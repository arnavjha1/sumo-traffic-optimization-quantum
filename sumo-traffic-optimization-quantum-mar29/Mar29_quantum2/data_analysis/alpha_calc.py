"""
Nearest-signal alpha exploration pipeline for Seattle SUMO traffic data.

This script does not calculate final alpha values yet. It assigns each usable
traffic count station to its nearest signalized intersection, keeps the station
only when that signal is close enough, and summarizes directional inflows.

Run from the repository root:

    python data_analysis/alpha_calc.py

or use the root-level wrapper:

    python estimate_alpha_exploration.py
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree


REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_COUNTS_CSV = REPO_ROOT / "data" / "Traffic_Study_Flow_Counts_Seattle.csv"
DEFAULT_SIGNALS_CSV = REPO_ROOT / "data" / "Traffic_Intersections_Seattle.csv"
DEFAULT_OUTPUT_CSV = (
    REPO_ROOT / "data_analysis" / "generated_data" / "alpha_nearest_signal_output.csv"
)

DIRECTION_COLUMNS = ["N", "S", "E", "W", "NE", "NW", "SE", "SW"]
DESCRIPTION_EXCLUDE_TERMS = ["DEAD END", "TRL", "RP", "ON RP", "OFF RP", "I5"]


def parse_args() -> argparse.Namespace:
    """Read command-line options while keeping repo-local defaults."""
    parser = argparse.ArgumentParser(
        description="Assign Seattle traffic count stations to their nearest signals."
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
        "--output-csv",
        type=Path,
        default=DEFAULT_OUTPUT_CSV,
        help="Path where the nearest-signal output CSV will be saved.",
    )
    parser.add_argument(
        "--max-distance-feet",
        type=float,
        default=150.0,
        help="Keep a station only if its nearest signal is within this distance.",
    )
    parser.add_argument(
        "--min-stations",
        type=int,
        default=2,
        help="Discard signals with fewer assigned stations than this.",
    )
    parser.add_argument(
        "--max-stations",
        type=int,
        default=12,
        help="Discard signals with more assigned stations than this.",
    )
    parser.add_argument(
        "--keep-nonstandard-signals",
        action="store_true",
        help="Do not discard descriptions containing DEAD END, TRL, RP, ON RP, OFF RP, or I5.",
    )
    return parser.parse_args()


def keep_available_columns(df: pd.DataFrame, desired_columns: Iterable[str]) -> pd.DataFrame:
    """Return only requested columns that exist in the source data."""
    available_columns = [column for column in desired_columns if column in df.columns]
    return df.loc[:, available_columns].copy()


def clean_number(series: pd.Series) -> pd.Series:
    """Convert values like '1,234' and blanks into numeric values."""
    return pd.to_numeric(
        series.astype("string").str.replace(",", "", regex=False).str.strip(),
        errors="coerce",
    )


def choose_volume_column(counts: pd.DataFrame) -> str:
    """Use STUDY_AWDT when present, otherwise fall back to STUDY_ADT."""
    if "STUDY_AWDT" in counts.columns:
        return "STUDY_AWDT"
    if "STUDY_ADT" in counts.columns:
        return "STUDY_ADT"
    raise ValueError("Traffic count data must include STUDY_AWDT or STUDY_ADT.")


def load_and_clean_counts(counts_csv: Path) -> pd.DataFrame:
    """Load traffic counts and keep stations with coordinates and positive volume."""
    desired_count_columns = [
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
    counts = keep_available_columns(raw_counts, desired_count_columns)

    volume_column = choose_volume_column(counts)
    counts["volume"] = clean_number(counts[volume_column])

    for coordinate_column in ["x", "y"]:
        if coordinate_column not in counts.columns:
            raise ValueError(f"Traffic count data is missing required coordinate {coordinate_column!r}.")
        counts[coordinate_column] = clean_number(counts[coordinate_column])

    if "STUDY_ID" not in counts.columns:
        counts["STUDY_ID"] = pd.NA

    if "STUDY_DIRFLOW" in counts.columns:
        counts["STUDY_DIRFLOW"] = counts["STUDY_DIRFLOW"].astype("string").str.upper().str.strip()
    else:
        counts["STUDY_DIRFLOW"] = pd.NA

    counts = counts.dropna(subset=["x", "y", "volume"])
    counts = counts[counts["volume"] > 0].copy()
    return counts.reset_index(drop=True)


def load_and_clean_signals(signals_csv: Path) -> pd.DataFrame:
    """Load signals and keep rows with projected coordinates."""
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

    if "UNITID" not in signals.columns:
        signals["UNITID"] = pd.NA
    if "UNITDESC" not in signals.columns:
        signals["UNITDESC"] = pd.NA
    if "SHAPE_LAT" not in signals.columns:
        signals["SHAPE_LAT"] = pd.NA
    if "SHAPE_LNG" not in signals.columns:
        signals["SHAPE_LNG"] = pd.NA

    signals = signals.dropna(subset=["GIS_XCOORD", "GIS_YCOORD"]).copy()
    return signals.reset_index(drop=True)


def estimate_alpha_from_directional_flows(row):
    """Placeholder for future left/straight/right movement classification."""
    return None, None, None


def assign_counts_to_nearest_signals(
    counts: pd.DataFrame,
    signals: pd.DataFrame,
    max_distance_feet: float,
) -> tuple[pd.DataFrame, int]:
    """
    Assign each count station to at most one signal.

    The KD-tree is built from signal coordinates in projected feet. Each station
    queries the tree for its single nearest signal. If that nearest signal is
    farther than max_distance_feet, the station is discarded instead of being
    attached to a distant or ambiguous intersection.
    """
    signal_points = signals[["GIS_XCOORD", "GIS_YCOORD"]].to_numpy(dtype=float)
    count_points = counts[["x", "y"]].to_numpy(dtype=float)

    signal_tree = cKDTree(signal_points)
    distances, signal_indexes = signal_tree.query(count_points, k=1)

    assigned = counts.copy()
    assigned["nearest_signal_index"] = signal_indexes
    assigned["station_distance_feet"] = distances

    within_distance = assigned["station_distance_feet"] <= max_distance_feet
    discarded_too_far = int((~within_distance).sum())
    assigned = assigned.loc[within_distance].copy()

    signal_lookup = signals.reset_index().rename(columns={"index": "nearest_signal_index"})
    assigned = assigned.merge(
        signal_lookup,
        on="nearest_signal_index",
        how="left",
        suffixes=("_count", "_signal"),
    )

    # The same STUDY_ID can appear more than once near the same signal. Keep the
    # closest copy so one study does not inflate an intersection's inflow.
    dedupe_columns = ["UNITID", "STUDY_ID"]
    assigned = assigned.sort_values("station_distance_feet")
    assigned = assigned.drop_duplicates(subset=dedupe_columns, keep="first")
    return assigned, discarded_too_far


def signal_description_is_allowed(description: object) -> bool:
    """Return False for optional nonstandard/ramp/trail/dead-end descriptions."""
    text = str(description).upper()
    return not any(term in text for term in DESCRIPTION_EXCLUDE_TERMS)


def summarize_assigned_signals(
    assigned: pd.DataFrame,
    max_distance_feet: float,
    min_stations: int,
    max_stations: int,
    discard_nonstandard_signals: bool,
) -> pd.DataFrame:
    """Group assigned stations by signal and apply quality filters."""
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
            row[f"total_{direction}_flow"] = float(group.loc[direction_mask, "volume"].sum())

        estimate_alpha_from_directional_flows(pd.Series(row))
        rows.append(row)

    output = pd.DataFrame(rows)
    if output.empty:
        return output

    quality_mask = (
        (output["assigned_count_stations"] >= min_stations)
        & (output["assigned_count_stations"] <= max_stations)
        & (output["max_station_distance"] <= max_distance_feet)
    )

    if discard_nonstandard_signals:
        quality_mask &= output["signal_description"].apply(signal_description_is_allowed)

    output = output.loc[quality_mask].copy()

    ordered_columns = [
        "signal_id",
        "signal_description",
        "latitude",
        "longitude",
        "assigned_count_stations",
        "u",
        "total_N_flow",
        "total_S_flow",
        "total_E_flow",
        "total_W_flow",
        "total_NE_flow",
        "total_NW_flow",
        "total_SE_flow",
        "total_SW_flow",
        "max_station_distance",
        "average_station_distance",
    ]
    return output.loc[:, ordered_columns].sort_values("u", ascending=False)


def print_summary(
    total_count_stations: int,
    assigned_count_stations: int,
    discarded_too_far: int,
    output: pd.DataFrame,
) -> None:
    """Print high-level diagnostics for nearest-signal assignment."""
    print("\nNearest-signal alpha exploration summary")
    print("========================================")
    print(f"Total count stations loaded: {total_count_stations:,}")
    print(f"Count stations assigned to a signal: {assigned_count_stations:,}")
    print(f"Count stations discarded for being farther than 150 ft: {discarded_too_far:,}")
    print(f"Number of valid signals after filtering: {len(output):,}")
    print(f"Mean estimated inflow u: {output['u'].mean():,.2f}")
    print(f"Median estimated inflow u: {output['u'].median():,.2f}")

    print("\nTop 10 valid intersections by estimated inflow")
    print("----------------------------------------------")
    display_columns = [
        "signal_id",
        "signal_description",
        "assigned_count_stations",
        "u",
        "max_station_distance",
    ]
    print(output.head(10)[display_columns].to_string(index=False))


def main() -> None:
    """Run the complete load, clean, assign, filter, print, and save pipeline."""
    args = parse_args()

    print(f"Loading traffic counts from: {args.counts_csv}")
    counts = load_and_clean_counts(args.counts_csv)
    print(f"Usable traffic count rows: {len(counts):,}")

    print(f"Loading signal inventory from: {args.signals_csv}")
    signals = load_and_clean_signals(args.signals_csv)
    print(f"Usable signal rows: {len(signals):,}")

    print(f"Assigning each count station to its nearest signal within {args.max_distance_feet:g} feet...")
    assigned, discarded_too_far = assign_counts_to_nearest_signals(
        counts=counts,
        signals=signals,
        max_distance_feet=args.max_distance_feet,
    )

    output = summarize_assigned_signals(
        assigned=assigned,
        max_distance_feet=args.max_distance_feet,
        min_stations=args.min_stations,
        max_stations=args.max_stations,
        discard_nonstandard_signals=not args.keep_nonstandard_signals,
    )

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(args.output_csv, index=False)

    print_summary(
        total_count_stations=len(counts),
        assigned_count_stations=len(assigned),
        discarded_too_far=discarded_too_far,
        output=output,
    )
    print(f"\nSaved nearest-signal output to: {args.output_csv}")


if __name__ == "__main__":
    main()
