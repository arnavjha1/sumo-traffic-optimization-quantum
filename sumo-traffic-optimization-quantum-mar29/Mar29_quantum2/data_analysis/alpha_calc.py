"""
Repeatable alpha-estimation pipeline for Seattle SUMO traffic data.

The source datasets do not contain true turn-level trajectories. This script
therefore estimates corridor continuation from directional count-station flows:
alpha_straight is the share of flow on the dominant opposing corridor, while
alpha_left and alpha_right split the remaining cross-flow evenly.

Run from the repository root:

    python data_analysis/alpha_calc.py

or use the root-level wrapper:

    python estimate_alpha_exploration.py
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree


REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_COUNTS_CSV = REPO_ROOT / "data" / "Traffic_Study_Flow_Counts_Seattle.csv"
DEFAULT_SIGNALS_CSV = REPO_ROOT / "data" / "Traffic_Intersections_Seattle.csv"
DEFAULT_GENERATED_DIR = REPO_ROOT / "data_analysis" / "generated_data"

DEFAULT_NEAREST_OUTPUT_CSV = DEFAULT_GENERATED_DIR / "alpha_nearest_signal_output.csv"
DEFAULT_CANDIDATE_OUTPUT_CSV = DEFAULT_GENERATED_DIR / "alpha_candidate_signals.csv"
DEFAULT_ALPHA_OUTPUT_CSV = DEFAULT_GENERATED_DIR / "alpha_estimates_by_signal.csv"
DEFAULT_CITYWIDE_SUMMARY_CSV = DEFAULT_GENERATED_DIR / "alpha_citywide_summary.csv"

DIRECTION_COLUMNS = ["N", "S", "E", "W", "NE", "NW", "SE", "SW"]
DIRECTION_FLOW_COLUMNS = [f"total_{direction}_flow" for direction in DIRECTION_COLUMNS]

CORRIDOR_PAIRS = {
    "NS": ("N", "S"),
    "EW": ("E", "W"),
    "NESW": ("NE", "SW"),
    "NWSE": ("NW", "SE"),
}

CANDIDATE_DESCRIPTION_EXCLUDE_TERMS = [
    "DEAD END",
    "TRL",
    "RP",
    "ON RP",
    "OFF RP",
    "I5",
    "BR",
    "SR",
    "POINT",
    "RAMP",
]


def parse_args() -> argparse.Namespace:
    """Read command-line options while keeping repo-local defaults."""
    parser = argparse.ArgumentParser(
        description="Estimate signal-level alpha values from Seattle traffic count flows."
    )
    parser.add_argument(
        "--counts-csv",
        type=Path,
        default=DEFAULT_COUNTS_CSV,
        help="Path to the Seattle traffic count CSV.",
    )
    parser.add_argument(
        "--signals-csv",
        type=Path,
        default=DEFAULT_SIGNALS_CSV,
        help="Path to the Seattle signal/intersection inventory CSV.",
    )
    parser.add_argument(
        "--nearest-output-csv",
        type=Path,
        default=DEFAULT_NEAREST_OUTPUT_CSV,
        help="Path where the full nearest-signal flow table will be saved.",
    )
    parser.add_argument(
        "--candidate-output-csv",
        type=Path,
        default=DEFAULT_CANDIDATE_OUTPUT_CSV,
        help="Path where candidate signals will be saved.",
    )
    parser.add_argument(
        "--alpha-output-csv",
        type=Path,
        default=DEFAULT_ALPHA_OUTPUT_CSV,
        help="Path where final per-signal alpha estimates will be saved.",
    )
    parser.add_argument(
        "--citywide-summary-csv",
        type=Path,
        default=DEFAULT_CITYWIDE_SUMMARY_CSV,
        help="Path where citywide alpha summary statistics will be saved.",
    )
    parser.add_argument(
        "--max-distance-feet",
        type=float,
        default=150.0,
        help="Assign a count station only if its nearest signal is within this distance.",
    )
    return parser.parse_args()


def keep_available_columns(df: pd.DataFrame, desired_columns: Iterable[str]) -> pd.DataFrame:
    """Return only requested columns that exist in the source data."""
    available_columns = [column for column in desired_columns if column in df.columns]
    return df.loc[:, available_columns].copy()


def clean_number(values: pd.Series) -> pd.Series:
    """Convert values like '1,234' and blanks into numeric values."""
    return pd.to_numeric(
        values.astype("string").str.replace(",", "", regex=False).str.strip(),
        errors="coerce",
    )


def choose_volume(counts: pd.DataFrame) -> pd.Series:
    """Prefer STUDY_AWDT as volume, falling back row-by-row to STUDY_ADT."""
    if "STUDY_AWDT" not in counts.columns and "STUDY_ADT" not in counts.columns:
        raise ValueError("Traffic count data must include STUDY_AWDT or STUDY_ADT.")

    awdt = clean_number(counts["STUDY_AWDT"]) if "STUDY_AWDT" in counts.columns else pd.Series(np.nan, index=counts.index)
    adt = clean_number(counts["STUDY_ADT"]) if "STUDY_ADT" in counts.columns else pd.Series(np.nan, index=counts.index)
    return awdt.fillna(adt)


def load_data(counts_csv: Path, signals_csv: Path) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """Load and clean traffic count stations and signalized intersections."""
    desired_count_columns = [
        "OBJECTID",
        "STUDY_ID",
        "STUDY_AWDT",
        "STUDY_ADT",
        "STUDY_DIRFLOW",
        "O_STREET",
        "X_STREET",
        "x",
        "y",
    ]
    raw_counts = pd.read_csv(counts_csv, low_memory=False)
    total_count_stations_loaded = len(raw_counts)
    counts = keep_available_columns(raw_counts, desired_count_columns)

    for coordinate_column in ["x", "y"]:
        if coordinate_column not in counts.columns:
            raise ValueError(f"Traffic count data is missing required coordinate {coordinate_column!r}.")
        counts[coordinate_column] = clean_number(counts[coordinate_column])

    counts["volume"] = choose_volume(counts)
    if "STUDY_DIRFLOW" in counts.columns:
        counts["STUDY_DIRFLOW"] = counts["STUDY_DIRFLOW"].astype("string").str.upper().str.strip()
    else:
        counts["STUDY_DIRFLOW"] = pd.NA

    counts = counts.dropna(subset=["x", "y", "volume"])
    counts = counts[counts["volume"] > 0].copy()
    counts = counts[counts["STUDY_DIRFLOW"].isin(DIRECTION_COLUMNS)].copy()

    desired_signal_columns = [
        "UNITID",
        "UNITDESC",
        "SHAPE_LAT",
        "SHAPE_LNG",
        "GIS_XCOORD",
        "GIS_YCOORD",
    ]
    raw_signals = pd.read_csv(signals_csv, low_memory=False)
    signals = keep_available_columns(raw_signals, desired_signal_columns)

    for coordinate_column in ["SHAPE_LAT", "SHAPE_LNG", "GIS_XCOORD", "GIS_YCOORD"]:
        if coordinate_column in signals.columns:
            signals[coordinate_column] = clean_number(signals[coordinate_column])

    if "GIS_XCOORD" not in signals.columns or "GIS_YCOORD" not in signals.columns:
        raise ValueError("Signal data must include GIS_XCOORD and GIS_YCOORD.")

    for optional_column in ["UNITID", "UNITDESC", "SHAPE_LAT", "SHAPE_LNG"]:
        if optional_column not in signals.columns:
            signals[optional_column] = pd.NA

    signals = signals.dropna(subset=["GIS_XCOORD", "GIS_YCOORD", "SHAPE_LAT", "SHAPE_LNG"]).copy()
    return counts.reset_index(drop=True), signals.reset_index(drop=True), total_count_stations_loaded


def assign_count_stations_to_nearest_signal(
    counts: pd.DataFrame,
    signals: pd.DataFrame,
    max_distance_feet: float = 150.0,
) -> tuple[pd.DataFrame, int]:
    """Assign each count station row to its nearest signal when within max distance."""
    signal_points = signals[["GIS_XCOORD", "GIS_YCOORD"]].to_numpy(dtype=float)
    count_points = counts[["x", "y"]].to_numpy(dtype=float)

    signal_tree = cKDTree(signal_points)
    distances, signal_indexes = signal_tree.query(count_points, k=1)

    assigned = counts.copy()
    assigned["nearest_signal_index"] = signal_indexes
    assigned["station_distance_feet"] = distances

    within_distance = assigned["station_distance_feet"] <= max_distance_feet
    discarded_count = int((~within_distance).sum())
    assigned = assigned.loc[within_distance].copy()

    signal_lookup = signals.reset_index().rename(columns={"index": "nearest_signal_index"})
    assigned = assigned.merge(
        signal_lookup,
        on="nearest_signal_index",
        how="left",
        suffixes=("_count", "_signal"),
    )
    return assigned.reset_index(drop=True), discarded_count


def direction_flow_column(direction: str) -> str:
    """Return the output column name for a direction's total flow."""
    return f"total_{direction}_flow"


def build_signal_flow_table(assigned: pd.DataFrame) -> pd.DataFrame:
    """Group assigned count stations by signal and summarize directional flows."""
    rows = []
    for _, group in assigned.groupby("UNITID", dropna=False):
        first = group.iloc[0]
        row = {
            "signal_id": first["UNITID"],
            "signal_description": first["UNITDESC"],
            "latitude": first["SHAPE_LAT"],
            "longitude": first["SHAPE_LNG"],
            "assigned_count_stations": int(len(group)),
            "u": float(group["volume"].sum()),
            "max_station_distance": float(group["station_distance_feet"].max()),
            "average_station_distance": float(group["station_distance_feet"].mean()),
        }

        for direction in DIRECTION_COLUMNS:
            direction_mask = group["STUDY_DIRFLOW"] == direction
            row[direction_flow_column(direction)] = float(group.loc[direction_mask, "volume"].sum())

        rows.append(row)

    output = pd.DataFrame(rows)
    if output.empty:
        columns = [
            "signal_id",
            "signal_description",
            "latitude",
            "longitude",
            "assigned_count_stations",
            "u",
            *DIRECTION_FLOW_COLUMNS,
            "max_station_distance",
            "average_station_distance",
            "nonzero_direction_buckets",
        ]
        return pd.DataFrame(columns=columns)

    output["nonzero_direction_buckets"] = output[DIRECTION_FLOW_COLUMNS].gt(0).sum(axis=1)
    ordered_columns = [
        "signal_id",
        "signal_description",
        "latitude",
        "longitude",
        "assigned_count_stations",
        "u",
        *DIRECTION_FLOW_COLUMNS,
        "max_station_distance",
        "average_station_distance",
        "nonzero_direction_buckets",
    ]
    return output.loc[:, ordered_columns].sort_values("u", ascending=False).reset_index(drop=True)


def signal_description_is_candidate(description: object) -> bool:
    """Return False for descriptions that look like ramps, bridges, trails, or links."""
    text = str(description).upper()
    return not any(term in text for term in CANDIDATE_DESCRIPTION_EXCLUDE_TERMS)


def filter_candidate_signals(signal_flows: pd.DataFrame, max_distance_feet: float = 150.0) -> pd.DataFrame:
    """Apply the candidate filters needed before estimating corridor alpha."""
    if signal_flows.empty:
        return signal_flows.copy()

    lower_u = signal_flows["u"].quantile(0.10)
    upper_u = signal_flows["u"].quantile(0.90)

    candidate_mask = (
        signal_flows["assigned_count_stations"].between(4, 8, inclusive="both")
        & (signal_flows["max_station_distance"] <= max_distance_feet)
        & (signal_flows["nonzero_direction_buckets"] >= 3)
        & signal_flows["u"].between(lower_u, upper_u, inclusive="both")
        & signal_flows["signal_description"].apply(signal_description_is_candidate)
    )
    return signal_flows.loc[candidate_mask].sort_values("u", ascending=False).reset_index(drop=True)


def analyze_direction_patterns(candidates: pd.DataFrame) -> pd.DataFrame:
    """Add opposing-pair flags and pair volumes for each candidate signal."""
    analyzed = candidates.copy()
    if analyzed.empty:
        for column in [
            "has_NS_pair",
            "has_EW_pair",
            "has_NESW_pair",
            "has_NWSE_pair",
            "NS_pair_volume",
            "EW_pair_volume",
            "NESW_pair_volume",
            "NWSE_pair_volume",
        ]:
            analyzed[column] = pd.Series(dtype=bool if column.startswith("has_") else float)
        return analyzed

    analyzed["has_NS_pair"] = (analyzed["total_N_flow"] > 0) & (analyzed["total_S_flow"] > 0)
    analyzed["has_EW_pair"] = (analyzed["total_E_flow"] > 0) & (analyzed["total_W_flow"] > 0)
    analyzed["has_NESW_pair"] = (analyzed["total_NE_flow"] > 0) & (analyzed["total_SW_flow"] > 0)
    analyzed["has_NWSE_pair"] = (analyzed["total_NW_flow"] > 0) & (analyzed["total_SE_flow"] > 0)

    for corridor, (first_direction, second_direction) in CORRIDOR_PAIRS.items():
        analyzed[f"{corridor}_pair_volume"] = (
            analyzed[direction_flow_column(first_direction)]
            + analyzed[direction_flow_column(second_direction)]
        )

    return analyzed


def estimate_corridor_alpha(analyzed_candidates: pd.DataFrame) -> pd.DataFrame:
    """Convert dominant-corridor continuation into estimated alpha values."""
    estimates = analyzed_candidates.copy()
    if estimates.empty:
        for column in [
            "dominant_corridor",
            "dominant_corridor_volume",
            "cross_flow_volume",
            "continuation_ratio",
            "departure_ratio",
            "alpha_left",
            "alpha_straight",
            "alpha_right",
        ]:
            estimates[column] = pd.Series(dtype=float)
        return estimates

    pair_volume_columns = [f"{corridor}_pair_volume" for corridor in CORRIDOR_PAIRS]
    dominant_pair_column = estimates[pair_volume_columns].idxmax(axis=1)
    estimates["dominant_corridor"] = dominant_pair_column.str.replace("_pair_volume", "", regex=False)
    estimates["dominant_corridor_volume"] = estimates[pair_volume_columns].max(axis=1)
    estimates["cross_flow_volume"] = (estimates["u"] - estimates["dominant_corridor_volume"]).clip(lower=0)
    estimates["continuation_ratio"] = estimates["dominant_corridor_volume"] / estimates["u"]
    estimates["departure_ratio"] = estimates["cross_flow_volume"] / estimates["u"]
    estimates["alpha_straight"] = estimates["continuation_ratio"]

    # The Seattle count data does not contain turn-level trajectories, so the
    # non-corridor departure share is split evenly into left and right estimates.
    estimates["alpha_left"] = estimates["departure_ratio"] / 2.0
    estimates["alpha_right"] = estimates["departure_ratio"] / 2.0
    return estimates


def build_citywide_summary(alpha_estimates: pd.DataFrame) -> pd.DataFrame:
    """Create one-row citywide alpha summary statistics."""
    summary = {
        "candidate_signal_count": int(len(alpha_estimates)),
        "mean_alpha_left": alpha_estimates["alpha_left"].mean(),
        "mean_alpha_straight": alpha_estimates["alpha_straight"].mean(),
        "mean_alpha_right": alpha_estimates["alpha_right"].mean(),
        "median_alpha_left": alpha_estimates["alpha_left"].median(),
        "median_alpha_straight": alpha_estimates["alpha_straight"].median(),
        "median_alpha_right": alpha_estimates["alpha_right"].median(),
        "mean_continuation_ratio": alpha_estimates["continuation_ratio"].mean(),
        "median_continuation_ratio": alpha_estimates["continuation_ratio"].median(),
        "mean_departure_ratio": alpha_estimates["departure_ratio"].mean(),
        "median_departure_ratio": alpha_estimates["departure_ratio"].median(),
    }
    return pd.DataFrame([summary])


def final_alpha_columns(alpha_estimates: pd.DataFrame) -> pd.DataFrame:
    """Return final alpha columns in the requested reusable order."""
    columns = [
        "signal_id",
        "signal_description",
        "u",
        "assigned_count_stations",
        "dominant_corridor",
        "dominant_corridor_volume",
        "cross_flow_volume",
        "continuation_ratio",
        "departure_ratio",
        "alpha_left",
        "alpha_straight",
        "alpha_right",
        "max_station_distance",
        "average_station_distance",
        *DIRECTION_FLOW_COLUMNS,
    ]
    return alpha_estimates.loc[:, columns].sort_values("u", ascending=False).reset_index(drop=True)


def write_outputs(
    signal_flows: pd.DataFrame,
    analyzed_candidates: pd.DataFrame,
    alpha_estimates: pd.DataFrame,
    citywide_summary: pd.DataFrame,
    nearest_output_csv: Path,
    candidate_output_csv: Path,
    alpha_output_csv: Path,
    citywide_summary_csv: Path,
) -> None:
    """Save all reusable CSV outputs, creating generated folders as needed."""
    os.makedirs(DEFAULT_GENERATED_DIR, exist_ok=True)
    for output_path in [
        nearest_output_csv,
        candidate_output_csv,
        alpha_output_csv,
        citywide_summary_csv,
    ]:
        output_path.parent.mkdir(parents=True, exist_ok=True)

    signal_flows.to_csv(nearest_output_csv, index=False)
    analyzed_candidates.to_csv(candidate_output_csv, index=False)
    final_alpha_columns(alpha_estimates).to_csv(alpha_output_csv, index=False)
    citywide_summary.to_csv(citywide_summary_csv, index=False)


def print_summaries(
    total_count_stations_loaded: int,
    count_stations_assigned: int,
    count_stations_discarded: int,
    signal_flows: pd.DataFrame,
    analyzed_candidates: pd.DataFrame,
    alpha_estimates: pd.DataFrame,
    citywide_summary: pd.DataFrame,
) -> None:
    """Print useful diagnostics and alpha summaries to console."""
    print("\nAlpha-estimation pipeline summary")
    print("=================================")
    print(f"Total count stations loaded: {total_count_stations_loaded:,}")
    print(f"Count stations assigned: {count_stations_assigned:,}")
    print(f"Count stations discarded: {count_stations_discarded:,}")
    print(f"Valid signals before candidate filtering: {len(signal_flows):,}")
    print(f"Candidate signal count: {len(analyzed_candidates):,}")

    ns_ew_count = int((analyzed_candidates["has_NS_pair"] & analyzed_candidates["has_EW_pair"]).sum()) if not analyzed_candidates.empty else 0
    pattern_counts = {
        "N + S": int(analyzed_candidates["has_NS_pair"].sum()) if not analyzed_candidates.empty else 0,
        "E + W": int(analyzed_candidates["has_EW_pair"].sum()) if not analyzed_candidates.empty else 0,
        "N + S + E + W": ns_ew_count,
        "NE + SW": int(analyzed_candidates["has_NESW_pair"].sum()) if not analyzed_candidates.empty else 0,
        "NW + SE": int(analyzed_candidates["has_NWSE_pair"].sum()) if not analyzed_candidates.empty else 0,
    }

    print("\nPattern counts")
    print("--------------")
    for pattern, count in pattern_counts.items():
        print(f"{pattern}: {count:,}")

    summary_row = citywide_summary.iloc[0]
    print("\nCitywide mean alpha")
    print("-------------------")
    print(
        "left={:.4f}, straight={:.4f}, right={:.4f}".format(
            summary_row["mean_alpha_left"],
            summary_row["mean_alpha_straight"],
            summary_row["mean_alpha_right"],
        )
    )
    print("\nCitywide median alpha")
    print("---------------------")
    print(
        "left={:.4f}, straight={:.4f}, right={:.4f}".format(
            summary_row["median_alpha_left"],
            summary_row["median_alpha_straight"],
            summary_row["median_alpha_right"],
        )
    )

    print("\nTop 10 candidate signals by u")
    print("-----------------------------")
    display_columns = [
        "signal_id",
        "signal_description",
        "u",
        "assigned_count_stations",
        "dominant_corridor",
        "continuation_ratio",
        "alpha_left",
        "alpha_straight",
        "alpha_right",
    ]
    if alpha_estimates.empty:
        print("(no candidate signals)")
    else:
        print(alpha_estimates.sort_values("u", ascending=False).head(10)[display_columns].to_string(index=False))


def main() -> None:
    """Run the full load, assign, summarize, filter, alpha, save, and print pipeline."""
    args = parse_args()

    counts, signals, total_count_stations_loaded = load_data(args.counts_csv, args.signals_csv)
    assigned, _count_stations_discarded_too_far = assign_count_stations_to_nearest_signal(
        counts=counts,
        signals=signals,
        max_distance_feet=args.max_distance_feet,
    )
    count_stations_discarded = total_count_stations_loaded - len(assigned)

    signal_flows = build_signal_flow_table(assigned)
    candidates = filter_candidate_signals(signal_flows, max_distance_feet=args.max_distance_feet)
    analyzed_candidates = analyze_direction_patterns(candidates)
    alpha_estimates = estimate_corridor_alpha(analyzed_candidates)
    citywide_summary = build_citywide_summary(alpha_estimates)

    write_outputs(
        signal_flows=signal_flows,
        analyzed_candidates=analyzed_candidates,
        alpha_estimates=alpha_estimates,
        citywide_summary=citywide_summary,
        nearest_output_csv=args.nearest_output_csv,
        candidate_output_csv=args.candidate_output_csv,
        alpha_output_csv=args.alpha_output_csv,
        citywide_summary_csv=args.citywide_summary_csv,
    )

    print_summaries(
        total_count_stations_loaded=total_count_stations_loaded,
        count_stations_assigned=len(assigned),
        count_stations_discarded=count_stations_discarded,
        signal_flows=signal_flows,
        analyzed_candidates=analyzed_candidates,
        alpha_estimates=alpha_estimates,
        citywide_summary=citywide_summary,
    )

    print("\nSaved outputs")
    print("-------------")
    print(args.nearest_output_csv)
    print(args.candidate_output_csv)
    print(args.alpha_output_csv)
    print(args.citywide_summary_csv)


if __name__ == "__main__":
    main()
