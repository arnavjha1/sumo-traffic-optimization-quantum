#!/usr/bin/env python3
"""Build reviewer-requested QAOA energy and traffic figures from current data.

The available JSON files contain one record per independent simulation run.
Energy fields in each record are averages across that run's 600 QAOA decision
epochs; individual epoch-level energy pairs were not persisted.  Accordingly,
the generated figures and captions explicitly identify the run as the unit of
analysis and do not imply an epoch-level distribution.

Default sources
---------------
* 2x2: quantum_data/quantum_simulation_results.json
* 3x3: quantum_data_3x3/quantum_3x3_simulation_results.json

Outputs include Figures 7-11 as PNG/PDF, manuscript-ready captions, a tidy
run-level CSV, bootstrap recovery estimates, and energy-traffic correlations.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from scipy import stats
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "This graph maker requires matplotlib, numpy, and scipy. Run it with "
        "the repository's qiskit_env Python environment."
    ) from exc


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_2X2 = ROOT / "quantum_data" / "quantum_simulation_results.json"
DEFAULT_3X3 = ROOT / "quantum_data_3x3" / "quantum_3x3_simulation_results.json"
DEFAULT_OUTPUT = ROOT / "graphs" / "reviewer_energy_traffic"

NETWORKS = ("2x2", "3x3")
NETWORK_LABELS = {"2x2": "2×2 Grid", "3x3": "3×3 Grid"}
NETWORK_COLORS = {"2x2": "#0072B2", "3x3": "#D55E00"}
EXACT_COLOR = "#4D4D4D"
QAOA_COLOR = "#CC79A7"
ALPHAS = tuple(round(index / 10, 1) for index in range(11))

RUN_FIELDS = (
    "average_selected_energy",
    "average_exact_min_energy",
    "average_optimality_gap",
    "optimum_recovery_rate",
    "average_travel_time",
    "average_waiting_time",
    "throughput",
    "num_decisions",
    "optimal_hits",
    "shots",
)

TRAFFIC_METRICS = (
    ("average_travel_time", "Average Travel Time (s)", "Travel time"),
    ("average_waiting_time", "Average Waiting Time (s)", "Waiting time"),
    ("throughput", "Throughput (vehicles)", "Throughput"),
)


@dataclass(frozen=True)
class RunRecord:
    network: str
    alpha: float
    condition: str
    run: int
    average_selected_energy: float
    average_exact_min_energy: float
    average_optimality_gap: float
    optimum_recovery_rate: float
    average_travel_time: float
    average_waiting_time: float
    throughput: float
    num_decisions: int
    optimal_hits: int
    shots: int

    def get(self, field: str) -> float:
        return float(getattr(self, field))


def load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read valid JSON from {path}: {exc}") from exc


def load_network(path: Path, network: str) -> list[RunRecord]:
    payload = load_json(path)
    records: list[RunRecord] = []
    for index, alpha in enumerate(ALPHAS):
        condition = f"a{index}"
        if condition not in payload:
            raise ValueError(f"Missing condition {condition} in {path}")
        entry = payload[condition]
        successful = int(entry.get("num_runs_successful", 0))
        runs = entry.get("runs", [])
        valid_runs = [run for run in runs if all(run.get(field) is not None for field in RUN_FIELDS)]
        if len(valid_runs) != successful:
            raise ValueError(
                f"{network} {condition}: {successful} successful runs reported but "
                f"{len(valid_runs)} complete run records found"
            )
        if successful < 2:
            raise ValueError(f"{network} {condition}: at least two complete runs are required")

        for run in valid_runs:
            record = RunRecord(
                network=network,
                alpha=alpha,
                condition=condition,
                run=int(run["run"]),
                average_selected_energy=float(run["average_selected_energy"]),
                average_exact_min_energy=float(run["average_exact_min_energy"]),
                average_optimality_gap=float(run["average_optimality_gap"]),
                optimum_recovery_rate=float(run["optimum_recovery_rate"]),
                average_travel_time=float(run["average_travel_time"]),
                average_waiting_time=float(run["average_waiting_time"]),
                throughput=float(run["throughput"]),
                num_decisions=int(run["num_decisions"]),
                optimal_hits=int(run["optimal_hits"]),
                shots=int(run["shots"]),
            )
            for field in RUN_FIELDS[:7]:
                if not math.isfinite(record.get(field)):
                    raise ValueError(f"{network} {condition} run {record.run}: non-finite {field}")
            records.append(record)
    return records


def values(records: Iterable[RunRecord], field: str) -> np.ndarray:
    return np.asarray([record.get(field) for record in records], dtype=float)


def select(records: Sequence[RunRecord], network: str, alpha: float | None = None) -> list[RunRecord]:
    return [
        record
        for record in records
        if record.network == network and (alpha is None or math.isclose(record.alpha, alpha))
    ]


def mean_ci(data: np.ndarray) -> tuple[float, float, float]:
    if data.size < 2:
        raise ValueError("At least two observations are required for a confidence interval")
    mean = float(np.mean(data))
    half_width = float(stats.t.ppf(0.975, data.size - 1) * stats.sem(data))
    return mean, mean - half_width, mean + half_width


def common_decision_count(records: Sequence[RunRecord]) -> int:
    counts = sorted({record.num_decisions for record in records})
    if len(counts) != 1:
        raise ValueError(f"Expected one common controller-evaluation count; found {counts}")
    return counts[0]


def bootstrap_mean_ci(data: np.ndarray, rng: np.random.Generator, resamples: int) -> tuple[float, float, float]:
    """Percentile CI from a cluster bootstrap over independent simulation runs."""
    if data.size < 2:
        raise ValueError("At least two runs are required for a bootstrap interval")
    draws = rng.choice(data, size=(resamples, data.size), replace=True)
    boot_means = np.mean(draws, axis=1)
    low, high = np.quantile(boot_means, [0.025, 0.975])
    return float(np.mean(data)), float(low), float(high)


def style_axis(ax: Any) -> None:
    ax.grid(True, color="#D7D7D7", linewidth=0.7, alpha=0.7)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(labelsize=8.5)


def alpha_ticks(ax: Any) -> None:
    ax.set_xticks(ALPHAS)
    ax.set_xticklabels([f"{alpha:.1f}" for alpha in ALPHAS], rotation=0)
    ax.set_xlim(-0.04, 1.04)
    ax.set_xlabel(r"Traffic demand parameter $\alpha$", fontsize=9.5)


def save_figure(fig: Any, output_dir: Path, stem: str, formats: list[str], dpi: int) -> list[Path]:
    paths: list[Path] = []
    for extension in formats:
        path = output_dir / f"{stem}.{extension}"
        kwargs: dict[str, Any] = {"bbox_inches": "tight"}
        if extension == "png":
            kwargs["dpi"] = dpi
        fig.savefig(path, **kwargs)
        paths.append(path)
    plt.close(fig)
    return paths


def draw_mean_ci(ax: Any, x: Sequence[float], summaries: Sequence[tuple[float, float, float]], **kwargs: Any) -> None:
    means = np.asarray([summary[0] for summary in summaries])
    lower = means - np.asarray([summary[1] for summary in summaries])
    upper = np.asarray([summary[2] for summary in summaries]) - means
    ax.errorbar(x, means, yerr=[lower, upper], capsize=3, capthick=1.1, markersize=4.8, **kwargs)


def figure7_energy_comparison(
    records: Sequence[RunRecord], output_dir: Path, formats: list[str], dpi: int
) -> list[Path]:
    fig, axes = plt.subplots(1, 2, figsize=(11.4, 4.8))
    for ax, network in zip(axes, NETWORKS):
        exact = [mean_ci(values(select(records, network, alpha), "average_exact_min_energy")) for alpha in ALPHAS]
        qaoa = [mean_ci(values(select(records, network, alpha), "average_selected_energy")) for alpha in ALPHAS]
        draw_mean_ci(
            ax,
            ALPHAS,
            exact,
            color=EXACT_COLOR,
            marker="s",
            linewidth=1.8,
            label=r"Exact classical minimum $E_{\min}$",
        )
        draw_mean_ci(
            ax,
            ALPHAS,
            qaoa,
            color=QAOA_COLOR,
            marker="o",
            linewidth=1.8,
            label=r"QAOA-selected $E_{\rm QAOA}$",
        )
        ax.fill_between(
            ALPHAS,
            [summary[0] for summary in exact],
            [summary[0] for summary in qaoa],
            color=QAOA_COLOR,
            alpha=0.09,
            label="Mean optimality gap",
        )
        ax.set_title(NETWORK_LABELS[network], fontsize=11)
        ax.set_ylabel("Run-average Ising energy", fontsize=9.5)
        alpha_ticks(ax)
        style_axis(ax)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, 0.91), ncol=3, frameon=False, fontsize=8.6)
    fig.suptitle("Exact Classical Global Minimum vs QAOA-Selected Energy", fontsize=14, y=0.985)
    fig.subplots_adjust(left=0.085, right=0.99, top=0.79, bottom=0.11, wspace=0.2)
    return save_figure(fig, output_dir, "figure7_exact_vs_qaoa_energy", formats, dpi)


def violin_with_summary(
    ax: Any,
    distributions: Sequence[np.ndarray],
    color: str,
    *,
    show_points: bool = False,
    jitter_seed: int = 0,
) -> None:
    positions = np.asarray(ALPHAS)
    violin = ax.violinplot(
        distributions,
        positions=positions,
        widths=0.075,
        showmeans=False,
        showmedians=False,
        showextrema=False,
    )
    for body in violin["bodies"]:
        body.set_facecolor(color)
        body.set_edgecolor(color)
        body.set_alpha(0.45)
        body.set_linewidth(0.8)
    medians = np.asarray([np.median(distribution) for distribution in distributions])
    q1 = np.asarray([np.quantile(distribution, 0.25) for distribution in distributions])
    q3 = np.asarray([np.quantile(distribution, 0.75) for distribution in distributions])
    ax.vlines(positions, q1, q3, color="#333333", linewidth=2.0, zorder=3)
    ax.scatter(positions, medians, color="white", edgecolor="#333333", linewidth=0.7, s=18, zorder=4)
    if show_points:
        rng = np.random.default_rng(jitter_seed)
        for position, distribution in zip(positions, distributions):
            jitter = np.clip(rng.normal(0.0, 0.012, size=distribution.size), -0.026, 0.026)
            ax.scatter(
                position + jitter,
                distribution,
                s=9,
                color="#222222",
                alpha=0.42,
                edgecolors="none",
                zorder=2,
            )


def figure8_gap_distribution(
    records: Sequence[RunRecord], output_dir: Path, formats: list[str], dpi: int
) -> list[Path]:
    fig, axes = plt.subplots(1, 2, figsize=(11.4, 4.8))
    for ax, network in zip(axes, NETWORKS):
        distributions = [values(select(records, network, alpha), "average_optimality_gap") for alpha in ALPHAS]
        violin_with_summary(ax, distributions, NETWORK_COLORS[network])
        ax.axhline(0, color="#666666", linestyle="--", linewidth=1.0)
        ax.set_title(NETWORK_LABELS[network], fontsize=11)
        ax.set_ylabel(r"Run-average optimality gap ($E_{\rm QAOA}-E_{\min}$)", fontsize=9.3)
        alpha_ticks(ax)
        style_axis(ax)
    fig.suptitle("QAOA Optimality-Gap Distributions", fontsize=14, y=0.985)
    fig.subplots_adjust(left=0.09, right=0.99, top=0.88, bottom=0.11, wspace=0.21)
    return save_figure(fig, output_dir, "figure8_optimality_gap_distribution", formats, dpi)


def figure9_recovery_probability(
    records: Sequence[RunRecord],
    output_dir: Path,
    formats: list[str],
    dpi: int,
    resamples: int,
    seed: int,
) -> tuple[list[Path], list[dict[str, Any]]]:
    fig, axes = plt.subplots(1, 2, figsize=(11.4, 4.8), sharey=True)
    rng = np.random.default_rng(seed)
    rows: list[dict[str, Any]] = []
    for ax, network in zip(axes, NETWORKS):
        summaries: list[tuple[float, float, float]] = []
        for alpha in ALPHAS:
            condition = select(records, network, alpha)
            data = values(condition, "optimum_recovery_rate")
            summary = bootstrap_mean_ci(data, rng, resamples)
            summaries.append(summary)
            rows.append(
                {
                    "network": network,
                    "alpha": alpha,
                    "n_runs": data.size,
                    "decisions_per_run": condition[0].num_decisions,
                    "mean_recovery_probability": summary[0],
                    "bootstrap_ci95_low": summary[1],
                    "bootstrap_ci95_high": summary[2],
                    "bootstrap_resamples": resamples,
                    "bootstrap_seed": seed,
                }
            )
        draw_mean_ci(
            ax,
            ALPHAS,
            summaries,
            color=NETWORK_COLORS[network],
            marker="o",
            linewidth=1.9,
        )
        ax.set_ylim(-0.03, 1.03)
        ax.set_title(NETWORK_LABELS[network], fontsize=11)
        ax.set_ylabel("Optimum-recovery probability", fontsize=9.5)
        alpha_ticks(ax)
        style_axis(ax)
    fig.suptitle("QAOA Optimum-Recovery Probability", fontsize=14, y=0.985)
    fig.subplots_adjust(left=0.085, right=0.99, top=0.88, bottom=0.11, wspace=0.18)
    return save_figure(fig, output_dir, "figure9_optimum_recovery_probability", formats, dpi), rows


def residualize_within_alpha(network_records: Sequence[RunRecord], field: str) -> np.ndarray:
    result = np.empty(len(network_records), dtype=float)
    for alpha in ALPHAS:
        indices = [index for index, record in enumerate(network_records) if math.isclose(record.alpha, alpha)]
        group = np.asarray([network_records[index].get(field) for index in indices], dtype=float)
        result[indices] = group - np.mean(group)
    return result


def partial_correlation(x: np.ndarray, y: np.ndarray, controls_df: int) -> tuple[float, float, int]:
    r = float(np.corrcoef(x, y)[0, 1])
    df = int(x.size - controls_df - 2)
    if df <= 0:
        raise ValueError("Insufficient residual degrees of freedom for partial correlation")
    t_value = r * math.sqrt(df / max(1e-15, 1.0 - r * r))
    p_value = float(2.0 * stats.t.sf(abs(t_value), df))
    return r, p_value, df


def format_p(p_value: float) -> str:
    return "$p<0.001$" if p_value < 0.001 else f"$p={p_value:.3f}$"


def figure10_energy_traffic_relationship(
    records: Sequence[RunRecord], output_dir: Path, formats: list[str], dpi: int
) -> tuple[list[Path], list[dict[str, Any]]]:
    fig, axes = plt.subplots(2, 3, figsize=(13.1, 7.3))
    rows: list[dict[str, Any]] = []
    for row_index, network in enumerate(NETWORKS):
        network_records = select(records, network)
        gap_residual = residualize_within_alpha(network_records, "average_optimality_gap")
        for column_index, (field, ylabel, short_label) in enumerate(TRAFFIC_METRICS):
            ax = axes[row_index, column_index]
            traffic_residual = residualize_within_alpha(network_records, field)
            fit = stats.linregress(gap_residual, traffic_residual)
            partial_r, p_value, correlation_df = partial_correlation(
                gap_residual, traffic_residual, controls_df=len(ALPHAS) - 1
            )
            x_line = np.linspace(float(np.min(gap_residual)), float(np.max(gap_residual)), 200)
            y_line = fit.intercept + fit.slope * x_line
            ax.scatter(
                gap_residual,
                traffic_residual,
                s=16,
                color=NETWORK_COLORS[network],
                alpha=0.48,
                edgecolors="none",
            )
            ax.plot(x_line, y_line, color="#222222", linewidth=1.6)
            ax.axhline(0, color="#999999", linewidth=0.8, linestyle="--")
            ax.axvline(0, color="#999999", linewidth=0.8, linestyle="--")
            ax.text(
                0.04,
                0.95,
                rf"within-$\alpha$ $r={partial_r:.2f}$" + "\n" + format_p(p_value) + f"\n$n={len(network_records)}$ runs",
                transform=ax.transAxes,
                ha="left",
                va="top",
                fontsize=8.3,
                bbox={"facecolor": "white", "edgecolor": "#CCCCCC", "alpha": 0.88, "pad": 3},
            )
            if row_index == 0:
                ax.set_title(short_label, fontsize=11)
            if column_index == 0:
                ax.text(
                    -0.28,
                    0.5,
                    NETWORK_LABELS[network],
                    transform=ax.transAxes,
                    rotation=90,
                    va="center",
                    ha="center",
                    fontsize=10.5,
                    fontweight="bold",
                )
            ax.set_xlabel(r"Within-$\alpha$ deviation in run-average gap", fontsize=8.8)
            ax.set_ylabel(rf"Within-$\alpha$ deviation in {ylabel.lower()}", fontsize=8.8)
            style_axis(ax)
            rows.append(
                {
                    "network": network,
                    "traffic_metric": field,
                    "n_runs": len(network_records),
                    "alpha_conditions_controlled": len(ALPHAS),
                    "within_alpha_pearson_r": partial_r,
                    "within_alpha_r_df": correlation_df,
                    "within_alpha_r_p_value": p_value,
                    "ols_slope_on_centered_data": float(fit.slope),
                    "ols_intercept_on_centered_data": float(fit.intercept),
                    "r_squared": partial_r**2,
                }
            )
    fig.suptitle("Within-Condition Energy–Traffic Relationship", fontsize=14, y=0.99)
    fig.subplots_adjust(left=0.105, right=0.99, top=0.92, bottom=0.08, wspace=0.29, hspace=0.34)
    return save_figure(fig, output_dir, "figure10_energy_traffic_relationship", formats, dpi), rows


def figure11_traffic_distributions(
    records: Sequence[RunRecord], output_dir: Path, formats: list[str], dpi: int
) -> list[Path]:
    fig, axes = plt.subplots(2, 3, figsize=(13.1, 7.2))
    for row_index, network in enumerate(NETWORKS):
        for column_index, (field, ylabel, short_label) in enumerate(TRAFFIC_METRICS):
            ax = axes[row_index, column_index]
            distributions = [values(select(records, network, alpha), field) for alpha in ALPHAS]
            violin_with_summary(
                ax,
                distributions,
                NETWORK_COLORS[network],
                show_points=True,
                jitter_seed=10_000 * (row_index + 1) + column_index,
            )
            if row_index == 0:
                ax.set_title(short_label, fontsize=11)
            if column_index == 0:
                ax.text(
                    -0.28,
                    0.5,
                    NETWORK_LABELS[network],
                    transform=ax.transAxes,
                    rotation=90,
                    va="center",
                    ha="center",
                    fontsize=10.5,
                    fontweight="bold",
                )
            ax.set_ylabel(ylabel, fontsize=9)
            alpha_ticks(ax)
            style_axis(ax)
    fig.suptitle("QAOA Traffic-Performance Distributions Across Repeated Runs", fontsize=14, y=0.99)
    fig.subplots_adjust(left=0.105, right=0.99, top=0.92, bottom=0.08, wspace=0.26, hspace=0.34)
    return save_figure(fig, output_dir, "figure11_qaoa_traffic_distributions", formats, dpi)


def write_csv(path: Path, rows: Sequence[dict[str, Any]]) -> Path:
    if not rows:
        raise ValueError(f"Cannot write empty CSV: {path}")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_run_level_csv(path: Path, records: Sequence[RunRecord]) -> Path:
    rows = [
        {
            "network": record.network,
            "alpha": record.alpha,
            "condition": record.condition,
            "run": record.run,
            "shots": record.shots,
            "num_decisions": record.num_decisions,
            "optimal_hits": record.optimal_hits,
            "optimum_recovery_rate": record.optimum_recovery_rate,
            "average_selected_energy": record.average_selected_energy,
            "average_exact_min_energy": record.average_exact_min_energy,
            "average_optimality_gap": record.average_optimality_gap,
            "average_travel_time": record.average_travel_time,
            "average_waiting_time": record.average_waiting_time,
            "throughput": record.throughput,
        }
        for record in records
    ]
    return write_csv(path, rows)


def write_captions(path: Path, resamples: int, seed: int, decisions: int) -> Path:
    text = (
        "figure7_exact_vs_qaoa_energy.png / .pdf\n"
        "Caption: Exact classical global minimum and QAOA-selected energy across traffic-demand conditions "
        "for the 2x2 and 3x3 grids. Points are means across 20 independent simulation runs per condition; "
        "error bars denote 95% confidence intervals across runs. Each plotted energy is the within-run mean "
        f"across {decisions} recorded QAOA controller evaluations (one per 1-s SUMO simulation step); shading "
        "denotes the difference between condition means.\n\n"
        "figure8_optimality_gap_distribution.png / .pdf\n"
        "Caption: Distribution of the QAOA optimality gap, E_QAOA - E_min, across repeated simulation runs. "
        "Each violin represents the distribution of run-level mean optimality gaps across 20 independent "
        "QAOA-controlled simulations per alpha condition; white points show medians and vertical bars show "
        f"interquartile ranges. Each run-level mean summarizes {decisions} recorded controller evaluations. "
        "Because evaluation-level energy pairs were not persisted, the violins describe repeated-run variation, "
        "not the distribution of individual controller-evaluation gaps.\n\n"
        "figure9_optimum_recovery_probability.png / .pdf\n"
        "Caption: QAOA optimum-recovery probability across traffic-demand conditions for the 2x2 and 3x3 "
        f"grids. Points show mean recovery rates across 20 independent runs per condition. Error bars are "
        f"percentile 95% confidence intervals from {resamples:,} cluster-bootstrap resamples of independent "
        f"simulation runs (seed={seed}); controller evaluations are not treated as independent replicates. "
        "Recovery is defined by energy equality with the exact optimum, "
        "1[|E_QAOA - E_min| <= 10^-9], so any minimum-energy bitstring counts as recovered.\n\n"
        "figure10_energy_traffic_relationship.png / .pdf\n"
        "Caption: Relationship between QAOA optimality gap and traffic outcomes across independent runs. "
        "Both the run-average gap and each traffic metric were centered within alpha condition before fitting. "
        "The displayed ordinary-least-squares lines and within-alpha Pearson correlations therefore measure "
        "run-to-run association after removing the 11 alpha-condition means. Correlation does not establish "
        "that energy quality causally changes traffic performance; effect magnitude should be considered alongside "
        "statistical significance.\n\n"
        "figure11_qaoa_traffic_distributions.png / .pdf\n"
        "Caption: Traffic-performance distributions across repeated QAOA-controlled simulation runs. "
        "Violins show 20 independent simulation runs per alpha condition for average travel time, average waiting "
        "time, and throughput; lightly jittered points show individual runs, white points show medians, and vertical "
        "bars show interquartile ranges.\n"
    )
    path.write_text(text, encoding="utf-8")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-2x2", type=Path, default=DEFAULT_2X2)
    parser.add_argument("--data-3x3", type=Path, default=DEFAULT_3X3)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--formats", nargs="+", choices=("png", "pdf", "svg"), default=["png", "pdf"])
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--bootstrap-resamples", type=int, default=10_000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260901)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.bootstrap_resamples < 1_000:
        raise ValueError("Use at least 1,000 bootstrap resamples for stable 95% intervals")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    records = load_network(args.data_2x2, "2x2") + load_network(args.data_3x3, "3x3")
    created: list[Path] = []
    created += figure7_energy_comparison(records, args.output_dir, args.formats, args.dpi)
    created += figure8_gap_distribution(records, args.output_dir, args.formats, args.dpi)
    figure9, recovery_rows = figure9_recovery_probability(
        records,
        args.output_dir,
        args.formats,
        args.dpi,
        args.bootstrap_resamples,
        args.bootstrap_seed,
    )
    created += figure9
    figure10, correlation_rows = figure10_energy_traffic_relationship(
        records, args.output_dir, args.formats, args.dpi
    )
    created += figure10
    created += figure11_traffic_distributions(records, args.output_dir, args.formats, args.dpi)
    created.append(write_run_level_csv(args.output_dir / "run_level_analysis_data.csv", records))
    created.append(write_csv(args.output_dir / "recovery_bootstrap_estimates.csv", recovery_rows))
    created.append(write_csv(args.output_dir / "energy_traffic_correlations.csv", correlation_rows))
    created.append(
        write_captions(
            args.output_dir / "figure_captions.txt",
            args.bootstrap_resamples,
            args.bootstrap_seed,
            common_decision_count(records),
        )
    )

    print(f"Validated {len(records)} complete runs: 220 for 2x2 and 220 for 3x3.")
    print("Created:")
    for path in created:
        print(f"  {path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
