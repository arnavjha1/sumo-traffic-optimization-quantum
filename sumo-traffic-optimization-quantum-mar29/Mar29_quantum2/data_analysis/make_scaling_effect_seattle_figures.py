#!/usr/bin/env python3
"""Build reviewer-requested scaling, effect-size, and Seattle summary figures.

The analysis is intentionally based only on saved experiment outputs; it does
not rerun SUMO or either optimizer.  QAOA uncertainty is calculated from the
available independent run-level results.  Classical Global is the exact,
deterministic comparator for the same network-wide Ising objective.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "graphs" / "reviewer_scaling_effect_seattle"

ALPHA_RESULTS = ROOT / "all_alpha_results.json"
SEATTLE_RESULTS = ROOT / "all_seattle_results.json"
QAOA_ALPHA = {
    "2x2": ROOT / "quantum_data" / "quantum_simulation_results.json",
    "3x3": ROOT / "quantum_data_3x3" / "quantum_3x3_simulation_results.json",
}
QAOA_SEATTLE = {
    "2x2": ROOT / "seattle_2x2_quantum_data" / "quantum_2x2_seattle_results.json",
    "3x3": ROOT / "seattle_3x3_quantum_data" / "quantum_3x3_seattle_results_20runs.json",
}

CONTROLLER_ORDER = (
    "fixed",
    "classical_local",
    "classical_global",
    "qaoa",
    "colight",
    "mplight",
    "presslight",
    "max_pressure",
    "scoot",
)
CONTROLLER_LABELS = {
    "fixed": "Fixed-Time",
    "classical_local": "Classical Local",
    "classical_global": "Classical Global",
    "qaoa": "QAOA",
    "colight": "CoLight",
    "mplight": "MPLight",
    "presslight": "PressLight",
    "max_pressure": "Max-Pressure",
    "scoot": "SCOOT",
}
CONTROLLER_COLORS = {
    "fixed": "#4C78A8",
    "classical_local": "#59A14F",
    "classical_global": "#1B7837",
    "qaoa": "#D62728",
    "colight": "#B279A2",
    "mplight": "#9467BD",
    "presslight": "#9C755F",
    "max_pressure": "#F28E2B",
    "scoot": "#76B7B2",
}
METRICS = {
    "average_travel_time": ("Average Travel Time (s)", False),
    "average_waiting_time": ("Average Waiting Time (s)", False),
    "throughput": ("Throughput (completed vehicles)", True),
}
SEATTLE_METRIC_KEYS = {
    "average_travel_time": "average_travel_time",
    "average_waiting_time": "average_waiting_time",
    "throughput": "completed_vehicles",
}
PEAK_HOURS = (16, 17)  # 4:00-6:00 PM, matching the Results-section description.


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def alpha_point(results: dict[str, Any], grid: str, controller: str, alpha: float) -> dict[str, float]:
    points = results["graph_data"][grid][controller]
    matches = [point for point in points if math.isclose(float(point["alpha"]), alpha)]
    if len(matches) != 1:
        raise ValueError(f"Expected one {grid}/{controller}/alpha={alpha} point, found {len(matches)}")
    return matches[0]


def qaoa_alpha_runs(results: dict[str, Any], alpha: float) -> list[dict[str, float]]:
    key = f"a{int(round(alpha * 10))}"
    runs = results[key]["runs"]
    if len(runs) < 2:
        raise ValueError(f"At least two QAOA runs are required for {key}")
    return runs


def qaoa_alpha_mean(results: dict[str, Any], alpha: float, metric: str) -> float:
    key = f"a{int(round(alpha * 10))}"
    return float(results[key]["statistics"][metric]["mean"])


def seattle_controller_data(results: dict[str, Any], grid: str, controller: str) -> dict[str, Any]:
    return results["graph_data"][grid][controller]


def weighted_hourly_value(hourly: Iterable[dict[str, Any]], metric: str, hours: tuple[int, ...]) -> float:
    selected = [row for row in hourly if int(row["hour"]) in hours]
    if len(selected) != len(hours):
        raise ValueError(f"Missing one or more peak hours {hours}")
    if metric == "completed_vehicles":
        return float(sum(float(row[metric]) for row in selected))
    weights = np.asarray([float(row["completed_vehicles"]) for row in selected], dtype=float)
    values = np.asarray([float(row[metric]) for row in selected], dtype=float)
    return float(np.average(values, weights=weights))


def bootstrap_mean_ci(values: np.ndarray, rng: np.random.Generator, draws: int) -> tuple[float, float, float]:
    if len(values) < 2:
        raise ValueError("Bootstrap confidence intervals require at least two values")
    samples = rng.choice(values, size=(draws, len(values)), replace=True)
    means = samples.mean(axis=1)
    low, high = np.percentile(means, [2.5, 97.5])
    return float(values.mean()), float(low), float(high)


def hedges_g_one_sample(improvements: np.ndarray) -> float:
    """Small-sample-corrected standardized improvement relative to zero."""
    n = len(improvements)
    sd = float(np.std(improvements, ddof=1))
    if math.isclose(sd, 0.0):
        return math.copysign(math.inf, float(np.mean(improvements)))
    correction = 1.0 - 3.0 / (4.0 * n - 5.0)
    return correction * float(np.mean(improvements)) / sd


def improvement_percent(qaoa: np.ndarray, classical: float, benefit_metric: bool) -> np.ndarray:
    if math.isclose(classical, 0.0):
        raise ValueError("The Classical Global comparator cannot be zero")
    direction = 1.0 if benefit_metric else -1.0
    return direction * (qaoa - classical) / classical * 100.0


def style_axis(ax: Any, *, xgrid: bool = True) -> None:
    ax.set_axisbelow(True)
    ax.grid(xgrid, axis="x", color="#D9D9D9", linewidth=0.7, alpha=0.85)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(labelsize=8.5)


def save_figure(fig: Any, output: Path, stem: str, formats: tuple[str, ...], dpi: int) -> list[Path]:
    paths: list[Path] = []
    for extension in formats:
        path = output / f"{stem}.{extension}"
        kwargs: dict[str, Any] = {"bbox_inches": "tight"}
        if extension == "png":
            kwargs["dpi"] = dpi
        fig.savefig(path, **kwargs)
        paths.append(path)
    plt.close(fig)
    return paths


def scaling_values(alpha_results: dict[str, Any], quantum: dict[str, dict[str, Any]], alpha: float) -> dict[str, dict[str, dict[str, float]]]:
    data: dict[str, dict[str, dict[str, float]]] = {}
    for grid in ("2x2", "3x3"):
        data[grid] = {}
        for controller in CONTROLLER_ORDER:
            if controller == "qaoa":
                data[grid][controller] = {
                    metric: qaoa_alpha_mean(quantum[grid], alpha, metric) for metric in METRICS
                }
            else:
                point = alpha_point(alpha_results, grid, controller, alpha)
                data[grid][controller] = {metric: float(point[metric]) for metric in METRICS}
    return data


def plot_scaling(data: dict[str, Any], alpha: float, output: Path, formats: tuple[str, ...], dpi: int) -> list[Path]:
    fig, axes = plt.subplots(1, 3, figsize=(13.2, 5.7), sharey=True)
    y = np.arange(len(CONTROLLER_ORDER))
    height = 0.34
    grid_styles = {"2x2": ("#A9C5DF", -height / 2), "3x3": ("#2F6B9A", height / 2)}
    for ax, metric in zip(axes, METRICS):
        for grid, (color, offset) in grid_styles.items():
            values = [data[grid][controller][metric] for controller in CONTROLLER_ORDER]
            ax.barh(y + offset, values, height=height, color=color, edgecolor="white", linewidth=0.4, label=grid)
        ax.set_xlabel(METRICS[metric][0], fontsize=9.5)
        ax.set_title(METRICS[metric][0].replace(" (completed vehicles)", ""), fontsize=11)
        style_axis(ax)
    axes[0].set_yticks(y, [CONTROLLER_LABELS[c] for c in CONTROLLER_ORDER])
    axes[0].invert_yaxis()
    handles = [
        Line2D([0], [0], color=color, linewidth=7, label=grid)
        for grid, (color, _) in grid_styles.items()
    ]
    fig.legend(handles=handles, frameon=False, loc="upper right", bbox_to_anchor=(0.985, 0.985), ncol=2)
    fig.suptitle(rf"Controller Scalability from 2$\times$2 to 3$\times$3 at $\alpha={alpha:.1f}$", fontsize=14, y=0.985)
    fig.text(0.5, 0.012, "Bars report observed values; QAOA bars are means across 20 independent runs.", ha="center", fontsize=8.7)
    fig.subplots_adjust(left=0.17, right=0.99, top=0.88, bottom=0.14, wspace=0.18)
    return save_figure(fig, output, "figure_scalability_2x2_to_3x3_alpha07", formats, dpi)


@dataclass(frozen=True)
class EffectRow:
    label: str
    group: str
    mean: float
    low: float
    high: float
    g: float
    n: int


def make_effect_rows(
    metric: str,
    alpha_results: dict[str, Any],
    quantum_alpha: dict[str, dict[str, Any]],
    seattle_results: dict[str, Any],
    quantum_seattle: dict[str, dict[str, Any]],
    rng: np.random.Generator,
    draws: int,
) -> list[EffectRow]:
    benefit = METRICS[metric][1]
    rows: list[EffectRow] = []
    for grid in ("2x2", "3x3"):
        for alpha in (0.5, 0.7, 1.0):
            classical = float(alpha_point(alpha_results, grid, "classical_global", alpha)[metric])
            qaoa = np.asarray([float(run[metric]) for run in qaoa_alpha_runs(quantum_alpha[grid], alpha)])
            improvements = improvement_percent(qaoa, classical, benefit)
            mean, low, high = bootstrap_mean_ci(improvements, rng, draws)
            rows.append(EffectRow(rf"{grid} $\alpha={alpha:.1f}$", "Saturated", mean, low, high, hedges_g_one_sample(improvements), len(qaoa)))

    seattle_key = SEATTLE_METRIC_KEYS[metric]
    for grid in ("2x2", "3x3"):
        classical_data = seattle_controller_data(seattle_results, grid, "classical_global")
        qaoa_runs = quantum_seattle[grid]["runs"]
        classical_full = float(classical_data["overall"][seattle_key])
        qaoa_full = np.asarray([float(run["overall_traffic"][seattle_key]) for run in qaoa_runs])
        full_improvement = improvement_percent(qaoa_full, classical_full, benefit)
        mean, low, high = bootstrap_mean_ci(full_improvement, rng, draws)
        rows.append(EffectRow(f"{grid} full day", "Seattle", mean, low, high, hedges_g_one_sample(full_improvement), len(qaoa_full)))

        classical_peak = weighted_hourly_value(classical_data["hourly"], seattle_key, PEAK_HOURS)
        qaoa_peak = np.asarray([
            weighted_hourly_value(run["hourly_traffic"], seattle_key, PEAK_HOURS) for run in qaoa_runs
        ])
        peak_improvement = improvement_percent(qaoa_peak, classical_peak, benefit)
        mean, low, high = bootstrap_mean_ci(peak_improvement, rng, draws)
        rows.append(EffectRow(f"{grid} PM peak", "Seattle", mean, low, high, hedges_g_one_sample(peak_improvement), len(qaoa_peak)))
    return rows


def effect_text(g: float) -> str:
    if math.isinf(g):
        return r"$g=\infty$"
    if abs(g) < 0.005:
        g = 0.0
    return rf"$g={g:.2f}$"


def plot_effects(effect_data: dict[str, list[EffectRow]], output: Path, formats: tuple[str, ...], dpi: int) -> list[Path]:
    fig, axes = plt.subplots(1, 3, figsize=(14.2, 6.8), sharey=True)
    metric_order = ("average_travel_time", "average_waiting_time", "throughput")
    colors = {"Saturated": "#4C78A8", "Seattle": "#D62728"}
    labels = [row.label for row in effect_data[metric_order[0]]]
    y = np.arange(len(labels))
    all_limits: list[float] = []
    for rows in effect_data.values():
        all_limits.extend([abs(row.low) for row in rows] + [abs(row.high) for row in rows])
    bound = max(all_limits) * 1.28
    for ax, metric in zip(axes, metric_order):
        rows = effect_data[metric]
        for index, row in enumerate(rows):
            ax.errorbar(
                row.mean,
                index,
                xerr=[[row.mean - row.low], [row.high - row.mean]],
                fmt="o",
                color=colors[row.group],
                ecolor=colors[row.group],
                capsize=3,
                markersize=5.5,
                linewidth=1.4,
                zorder=3,
            )
            text_x = row.high + 0.02 * bound
            ax.text(text_x, index, effect_text(row.g), va="center", ha="left", fontsize=7.6, color="#333333")
        ax.axvline(0.0, color="#555555", linewidth=1.0)
        ax.set_xlim(-bound, bound)
        ax.set_title(METRICS[metric][0].replace(" (completed vehicles)", ""), fontsize=11)
        ax.set_xlabel("QAOA improvement over Classical Global (%)", fontsize=9.2)
        style_axis(ax)
    axes[0].set_yticks(y, labels)
    axes[0].invert_yaxis()
    handles = [Line2D([0], [0], marker="o", color=color, linestyle="none", label=group) for group, color in colors.items()]
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, 0.925), ncol=2, frameon=False)
    fig.suptitle("QAOA Improvement Relative to Exact Classical Global Optimization", fontsize=14, y=0.985)
    fig.text(
        0.5,
        0.012,
        "Points are mean percentage improvements; bars are percentile-bootstrap 95% CIs (10,000 resamples). "
        "Positive values favor QAOA. Labels report one-sample Hedges' g; each QAOA condition uses n=20 runs. "
        "Seattle PM peak is 4-6 PM.",
        ha="center",
        fontsize=8.4,
    )
    fig.subplots_adjust(left=0.17, right=0.985, top=0.86, bottom=0.16, wspace=0.15)
    return save_figure(fig, output, "figure_qaoa_vs_classical_global_bootstrap_effect", formats, dpi)


def seattle_summary(
    seattle_results: dict[str, Any], quantum_seattle: dict[str, dict[str, Any]]
) -> dict[str, dict[str, dict[str, tuple[float, float | None]]]]:
    data: dict[str, dict[str, dict[str, tuple[float, float | None]]]] = {}
    for grid in ("2x2", "3x3"):
        data[grid] = {}
        for controller in CONTROLLER_ORDER:
            data[grid][controller] = {}
            if controller == "qaoa":
                stats = quantum_seattle[grid]["overall_traffic_statistics"]
                for metric, seattle_key in SEATTLE_METRIC_KEYS.items():
                    data[grid][controller][metric] = (
                        float(stats[seattle_key]["mean"]),
                        float(stats[seattle_key]["standard_deviation"]),
                    )
            else:
                overall = seattle_controller_data(seattle_results, grid, controller)["overall"]
                for metric, seattle_key in SEATTLE_METRIC_KEYS.items():
                    data[grid][controller][metric] = (float(overall[seattle_key]), None)
    return data


def plot_seattle(data: dict[str, Any], output: Path, formats: tuple[str, ...], dpi: int) -> list[Path]:
    fig, axes = plt.subplots(2, 3, figsize=(13.4, 8.1), sharey=True)
    y = np.arange(len(CONTROLLER_ORDER))
    metrics = ("average_travel_time", "average_waiting_time", "throughput")
    for row, grid in enumerate(("2x2", "3x3")):
        for column, metric in enumerate(metrics):
            ax = axes[row, column]
            values = [data[grid][c][metric][0] for c in CONTROLLER_ORDER]
            errors = [data[grid][c][metric][1] or 0.0 for c in CONTROLLER_ORDER]
            colors = [CONTROLLER_COLORS[c] for c in CONTROLLER_ORDER]
            ax.barh(y, values, color=colors, edgecolor="white", linewidth=0.4, xerr=errors, capsize=2.5, error_kw={"elinewidth": 1.0})
            if row == 0:
                ax.set_title(METRICS[metric][0].replace(" (completed vehicles)", ""), fontsize=11)
            ax.set_xlabel(METRICS[metric][0], fontsize=9.2)
            style_axis(ax)
            if column == 0:
                ax.set_ylabel(f"{grid} network", fontsize=10.5, labelpad=8)
    for ax in axes[:, 0]:
        ax.set_yticks(y, [CONTROLLER_LABELS[c] for c in CONTROLLER_ORDER])
    axes[0, 0].invert_yaxis()
    fig.suptitle("Seattle Full-Day Aggregate Controller Comparison", fontsize=14, y=0.985)
    fig.text(0.5, 0.012, "QAOA bars show means and one standard deviation across 20 independent runs; other controllers are single deterministic runs.", ha="center", fontsize=8.5)
    fig.subplots_adjust(left=0.17, right=0.99, top=0.92, bottom=0.10, wspace=0.18, hspace=0.29)
    return save_figure(fig, output, "figure_seattle_all_controller_aggregate", formats, dpi)


def fmt_value(value: float, sd: float | None, metric: str, bold: bool) -> str:
    decimals = 0 if metric == "throughput" else 2
    if sd is None:
        body = f"{value:.{decimals}f}"
    else:
        body = f"{value:.{decimals}f} $\\pm$ {sd:.{decimals}f}"
    return rf"\textbf{{{body}}}" if bold else body


def write_latex_table(data: dict[str, Any], output: Path) -> Path:
    best: dict[tuple[str, str], float] = {}
    for grid in ("2x2", "3x3"):
        for metric in METRICS:
            values = [data[grid][controller][metric][0] for controller in CONTROLLER_ORDER]
            best[(grid, metric)] = max(values) if METRICS[metric][1] else min(values)

    lines = [
        r"\begin{table*}[htbp]",
        r"\centering",
        r"\caption{Full-day Seattle aggregate performance for all nine controllers on the $2\times2$ and $3\times3$ networks. Travel and waiting time are cost metrics; completed vehicles is a benefit metric. QAOA entries report mean $\pm$ standard deviation across 20 independent runs, whereas the other entries are single deterministic runs. Bold denotes the best observed value within each network and metric.}",
        r"\label{tab:seattle-all-controller-aggregate}",
        r"\resizebox{\textwidth}{!}{%",
        r"\begin{tabular}{lrrrrrr}",
        r"\toprule",
        r"& \multicolumn{3}{c}{$2\times2$ network} & \multicolumn{3}{c}{$3\times3$ network} \\",
        r"\cmidrule(lr){2-4}\cmidrule(lr){5-7}",
        r"Controller & Travel Time (s) & Waiting Time (s) & Completed Vehicles & Travel Time (s) & Waiting Time (s) & Completed Vehicles \\",
        r"\midrule",
    ]
    for controller in CONTROLLER_ORDER:
        cells = [CONTROLLER_LABELS[controller]]
        for grid in ("2x2", "3x3"):
            for metric in ("average_travel_time", "average_waiting_time", "throughput"):
                value, sd = data[grid][controller][metric]
                is_best = math.isclose(value, best[(grid, metric)], rel_tol=1e-12, abs_tol=1e-12)
                cells.append(fmt_value(value, sd, metric, is_best))
        lines.append(" & ".join(cells) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}%", r"}", r"\end{table*}", ""]
    path = output / "seattle_all_controller_aggregate_table.tex"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_summary_csv(data: dict[str, Any], output: Path) -> Path:
    path = output / "seattle_all_controller_aggregate_data.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["network", "controller", "metric", "value", "standard_deviation", "qaoa_runs"])
        for grid in ("2x2", "3x3"):
            for controller in CONTROLLER_ORDER:
                for metric in METRICS:
                    value, sd = data[grid][controller][metric]
                    writer.writerow([grid, CONTROLLER_LABELS[controller], metric, f"{value:.8g}", "" if sd is None else f"{sd:.8g}", 20 if controller == "qaoa" else ""])
    return path


def write_effect_csv(effect_data: dict[str, list[EffectRow]], output: Path) -> Path:
    path = output / "qaoa_vs_classical_global_bootstrap_effect_data.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "condition", "group", "mean_improvement_percent", "ci95_low", "ci95_high", "hedges_g", "n"])
        for metric, rows in effect_data.items():
            for row in rows:
                writer.writerow([metric, row.label.replace("$", ""), row.group, row.mean, row.low, row.high, row.g, row.n])
    return path


def write_captions(output: Path) -> Path:
    text = (
        "Figure 1. Direct controller scalability from the 2x2 to the 3x3 network at alpha=0.7. "
        "Each panel reports the observed value for average travel time, average waiting time, or throughput. "
        "QAOA values are means across 20 independent runs; all other values are from the saved deterministic controller runs.\n\n"
        "Figure 2. QAOA improvement relative to the exact Classical Global controller for travel time, waiting time, and throughput. "
        "Positive values favor QAOA. Points denote mean percentage improvement and horizontal bars denote percentile-bootstrap 95% confidence intervals from 10,000 resamples of the 20 independent QAOA runs. "
        "Annotations report one-sample Hedges' g relative to the deterministic Classical Global benchmark. Seattle PM peak covers 4-6 PM (hours 16-17).\n\n"
        "Figure 3. Full-day Seattle aggregate performance for all nine controllers on the 2x2 and 3x3 networks. "
        "QAOA bars report means with one-standard-deviation error bars across 20 independent runs; the other controllers are single deterministic runs.\n"
    )
    path = output / "figure_captions.txt"
    path.write_text(text, encoding="utf-8")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--formats", nargs="+", choices=("png", "pdf", "svg"), default=("png", "pdf"))
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--bootstrap-draws", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20260901)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    alpha_results = load_json(ALPHA_RESULTS)
    seattle_results = load_json(SEATTLE_RESULTS)
    quantum_alpha = {grid: load_json(path) for grid, path in QAOA_ALPHA.items()}
    quantum_seattle = {grid: load_json(path) for grid, path in QAOA_SEATTLE.items()}

    created: list[Path] = []
    scaling = scaling_values(alpha_results, quantum_alpha, 0.7)
    created += plot_scaling(scaling, 0.7, args.output_dir, tuple(args.formats), args.dpi)

    rng = np.random.default_rng(args.seed)
    effect_data = {
        metric: make_effect_rows(metric, alpha_results, quantum_alpha, seattle_results, quantum_seattle, rng, args.bootstrap_draws)
        for metric in METRICS
    }
    created += plot_effects(effect_data, args.output_dir, tuple(args.formats), args.dpi)
    created.append(write_effect_csv(effect_data, args.output_dir))

    seattle = seattle_summary(seattle_results, quantum_seattle)
    created += plot_seattle(seattle, args.output_dir, tuple(args.formats), args.dpi)
    created.append(write_latex_table(seattle, args.output_dir))
    created.append(write_summary_csv(seattle, args.output_dir))
    created.append(write_captions(args.output_dir))

    print("Created:")
    for path in created:
        print(f"  {path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
