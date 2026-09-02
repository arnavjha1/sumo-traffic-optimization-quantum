#!/usr/bin/env python3
"""Generate publication-ready QAOA sensitivity figures from experiment JSON.

The script reads the per-condition result files produced by
``hyper_runner_3x3.py`` and ``noise_runner_3x3.py``.  By default it also uses
the ``a7`` entry in the existing 3x3 aggregate results as the ideal/no-noise
reference.  No simulation is rerun.

Examples
--------
    python data_analysis/make_quantum_sensitivity_figures.py
    python data_analysis/make_quantum_sensitivity_figures.py --formats png pdf
    python data_analysis/make_quantum_sensitivity_figures.py --no-ideal-baseline
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from scipy.stats import t as student_t
except ImportError as exc:  # pragma: no cover - exercised only on bad environments
    raise SystemExit(
        "This graph maker requires matplotlib and scipy. Run it with the "
        "repository's qiskit_env Python environment."
    ) from exc


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HYPER_DIR = ROOT / "quantum_hyperparameter_data_3x3"
DEFAULT_NOISE_DIR = ROOT / "quantum_noise_data_3x3"
DEFAULT_IDEAL_DATA = ROOT / "quantum_data_3x3" / "quantum_3x3_simulation_results.json"
DEFAULT_OUTPUT_DIR = ROOT / "graphs" / "quantum_sensitivity_3x3"

HYPER_ORDER = ("beta", "gamma", "p", "shots")
HYPER_TITLES = {
    "beta": r"$\beta$ (mixer angle)",
    "gamma": r"$\gamma$ (cost angle)",
    "p": r"$p$ (circuit depth)",
    "shots": "shots",
}
HYPER_BASELINE_KEYS = {
    "beta": "beta",
    "gamma": "gamma",
    "p": "p",
    "shots": "shots",
}
NOISE_ORDER = ("angle", "depolarizing", "readout")
NOISE_TITLES = {
    "angle": "Angle Noise",
    "depolarizing": "Depolarizing Noise",
    "readout": "Readout Noise",
}

METRICS = {
    "travel": ("average_travel_time", "Avg Travel Time (s)"),
    "waiting": ("average_waiting_time", "Avg Waiting Time (s)"),
    "recovery": ("optimum_recovery_rate", "Optimum Recovery Rate"),
    "gap": ("average_optimality_gap", "Avg Optimality Gap"),
}

COLORS = {
    "travel": "#1f77b4",
    "waiting": "#ff7f0e",
    "recovery": "#2ca02c",
    "gap": "#d62728",
    "baseline": "#4d4d4d",
}


@dataclass(frozen=True)
class Point:
    value: float
    mean: float
    ci_low: float
    ci_high: float
    n: int
    label: str = ""

    @property
    def yerr(self) -> list[list[float]]:
        return [[self.mean - self.ci_low], [self.ci_high - self.mean]]


def load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read valid JSON from {path}: {exc}") from exc


def ci_from_stat(stat: dict[str, Any], n: int) -> tuple[float, float, float]:
    """Return mean and a two-sided 95% Student-t confidence interval."""
    mean = float(stat["mean"])
    if "ci95_low" in stat and "ci95_high" in stat:
        return mean, float(stat["ci95_low"]), float(stat["ci95_high"])
    if n < 2:
        raise ValueError("At least two independent runs are required for a 95% CI")
    standard_error = float(stat["standard_error"])
    half_width = float(student_t.ppf(0.975, df=n - 1)) * standard_error
    return mean, mean - half_width, mean + half_width


def point_from_result(result: dict[str, Any], metric_key: str, value: float, label: str = "") -> Point:
    experiment = result["experiment"]
    n = int(experiment["num_runs_successful"])
    mean, low, high = ci_from_stat(result["statistics"][metric_key], n)
    return Point(float(value), mean, low, high, n, label)


def load_hyperparameter_data(directory: Path) -> tuple[dict[str, dict[str, Any]], dict[str, float]]:
    grouped: dict[str, dict[str, Any]] = {name: {} for name in HYPER_ORDER}
    baseline: dict[str, float] | None = None
    files = sorted(directory.glob("*_value*_results.json"))
    if not files:
        raise ValueError(f"No hyperparameter result JSON files found in {directory}")

    for path in files:
        result = load_json(path)
        experiment = result.get("experiment", {})
        hyper = str(experiment.get("hyperparameter", ""))
        condition = str(experiment.get("condition_name", ""))
        if hyper not in grouped or not condition:
            continue
        grouped[hyper][condition] = result
        current = {key: float(value) for key, value in experiment["baseline_configuration"].items()}
        if baseline is None:
            baseline = current
        elif current != baseline:
            raise ValueError(f"Inconsistent baseline configuration in {path}")

    missing = [name for name, results in grouped.items() if len(results) != 3]
    if missing:
        raise ValueError(f"Expected exactly three conditions for: {', '.join(missing)}")
    assert baseline is not None
    return grouped, baseline


def load_noise_data(directory: Path) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {name: {} for name in NOISE_ORDER}
    files = sorted(directory.glob("*_results.json"))
    if not files:
        raise ValueError(f"No noise result JSON files found in {directory}")

    for path in files:
        # The all-level files duplicate the per-level data and are intentionally
        # ignored so every plotted point has one authoritative source file.
        if "_all_levels_" in path.name:
            continue
        result = load_json(path)
        experiment = result.get("experiment", {})
        noise_type = str(experiment.get("noise_type", ""))
        level = str(experiment.get("level_name", ""))
        if noise_type not in grouped or not level:
            continue
        grouped[noise_type][level] = result

    missing = [name for name, results in grouped.items() if set(results) != {"low", "medium", "high"}]
    if missing:
        raise ValueError(f"Expected low/medium/high conditions for: {', '.join(missing)}")
    return grouped


def load_ideal_baseline(path: Path, alpha_key: str, metric_key: str) -> Point:
    aggregate = load_json(path)
    if alpha_key not in aggregate:
        raise ValueError(f"Ideal baseline key {alpha_key!r} is absent from {path}")
    result = aggregate[alpha_key]
    n = int(result["num_runs_successful"])
    mean, low, high = ci_from_stat(result["statistics"][metric_key], n)
    return Point(0.0, mean, low, high, n, "Ideal (0)")


def errorbar(ax: Any, points: Iterable[Point], color: str, *, baseline_n: int | None = None) -> None:
    points = list(points)
    x = [point.value for point in points]
    y = [point.mean for point in points]
    lower = [point.mean - point.ci_low for point in points]
    upper = [point.ci_high - point.mean for point in points]
    ax.errorbar(
        x,
        y,
        yerr=[lower, upper],
        color=color,
        marker="o",
        markersize=5.2,
        linewidth=1.8,
        capsize=3.2,
        capthick=1.1,
        zorder=3,
    )
    if baseline_n is not None and points and math.isclose(points[0].value, 0.0):
        point = points[0]
        ax.errorbar(
            [point.value],
            [point.mean],
            yerr=point.yerr,
            color=COLORS["baseline"],
            marker="D",
            markersize=5.5,
            linewidth=0,
            elinewidth=1.4,
            capsize=3.2,
            capthick=1.1,
            zorder=4,
        )


def style_axis(ax: Any) -> None:
    ax.grid(True, axis="both", color="#d7d7d7", linewidth=0.7, alpha=0.7)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(labelsize=8.5)


def format_hyper_value(hyper: str, value: float) -> str:
    if hyper in {"p", "shots"}:
        return str(int(round(value)))
    return f"{value:.3f}"


def noise_tick_label(noise_type: str, value: float) -> str:
    if math.isclose(value, 0.0):
        return "0"
    if noise_type == "angle":
        return f"{value:g}"
    return f"{100.0 * value:g}%"


def save_figure(fig: Any, output_dir: Path, stem: str, formats: list[str], dpi: int) -> list[Path]:
    paths: list[Path] = []
    for extension in formats:
        path = output_dir / f"{stem}.{extension}"
        kwargs = {"bbox_inches": "tight"}
        if extension.lower() == "png":
            kwargs["dpi"] = dpi
        fig.savefig(path, **kwargs)
        paths.append(path)
    plt.close(fig)
    return paths


def hyper_points(results: dict[str, Any], metric_key: str) -> list[Point]:
    points = [
        point_from_result(result, metric_key, float(result["experiment"]["hyperparameter_value"]))
        for result in results.values()
    ]
    return sorted(points, key=lambda point: point.value)


def plot_hyperparameter_figure(
    grouped: dict[str, dict[str, Any]],
    baseline: dict[str, float],
    metrics: tuple[str, str],
    title: str,
    stem: str,
    output_dir: Path,
    formats: list[str],
    dpi: int,
) -> list[Path]:
    fig, axes = plt.subplots(2, 4, figsize=(13.6, 6.3), sharey="row", constrained_layout=False)
    sample_sizes: set[int] = set()
    for column, hyper in enumerate(HYPER_ORDER):
        for row, metric_name in enumerate(metrics):
            metric_key, ylabel = METRICS[metric_name]
            points = hyper_points(grouped[hyper], metric_key)
            sample_sizes.update(point.n for point in points)
            ax = axes[row, column]
            errorbar(ax, points, COLORS[metric_name])
            ax.axvline(
                float(baseline[HYPER_BASELINE_KEYS[hyper]]),
                color="#8c8c8c",
                linestyle="--",
                linewidth=1.2,
                zorder=1,
            )
            values = [point.value for point in points]
            ax.set_xticks(values, [format_hyper_value(hyper, value) for value in values])
            ax.set_xlabel(HYPER_TITLES[hyper], fontsize=9.5)
            if row == 0:
                ax.set_title(HYPER_TITLES[hyper], fontsize=11, pad=7)
            if column == 0:
                ax.set_ylabel(f"{ylabel}\n(95% CI)", fontsize=9.5)
            style_axis(ax)

    if len(sample_sizes) != 1:
        raise ValueError(f"Hyperparameter conditions have inconsistent sample sizes: {sorted(sample_sizes)}")
    fig.suptitle(title, fontsize=14, y=0.985)
    fig.subplots_adjust(left=0.075, right=0.99, top=0.88, bottom=0.10, wspace=0.18, hspace=0.32)
    return save_figure(fig, output_dir, stem, formats, dpi)


def noise_points(results: dict[str, Any], metric_key: str, ideal: Point | None) -> list[Point]:
    points: list[Point] = [] if ideal is None else [ideal]
    for level in ("low", "medium", "high"):
        result = results[level]
        points.append(
            point_from_result(
                result,
                metric_key,
                float(result["experiment"]["noise_level"]),
                level.title(),
            )
        )
    return points


def plot_noise_figure(
    grouped: dict[str, dict[str, Any]],
    ideal_data: Path | None,
    alpha_key: str,
    metrics: tuple[str, str],
    title: str,
    stem: str,
    output_dir: Path,
    formats: list[str],
    dpi: int,
) -> tuple[list[Path], int, int | None]:
    fig, axes = plt.subplots(2, 3, figsize=(12.6, 6.5), sharey="row", constrained_layout=False)
    noisy_sample_sizes: set[int] = set()
    ideal_n: int | None = None

    for column, noise_type in enumerate(NOISE_ORDER):
        for row, metric_name in enumerate(metrics):
            metric_key, ylabel = METRICS[metric_name]
            ideal = load_ideal_baseline(ideal_data, alpha_key, metric_key) if ideal_data else None
            if ideal is not None:
                ideal_n = ideal.n
            points = noise_points(grouped[noise_type], metric_key, ideal)
            noisy_sample_sizes.update(point.n for point in points if not math.isclose(point.value, 0.0))
            ax = axes[row, column]
            errorbar(ax, points, COLORS[metric_name], baseline_n=ideal_n)
            values = [point.value for point in points]
            ax.set_xticks(values, [noise_tick_label(noise_type, value) for value in values])
            if noise_type == "angle":
                xlabel = r"Angle-noise $\sigma$ (rad)"
            else:
                xlabel = f"{NOISE_TITLES[noise_type].replace(' Noise', '')} probability"
            ax.set_xlabel(xlabel, fontsize=9.5)
            if row == 0:
                ax.set_title(NOISE_TITLES[noise_type], fontsize=11, pad=7)
            if column == 0:
                ax.set_ylabel(f"{ylabel}\n(95% CI)", fontsize=9.5)
            style_axis(ax)

    if len(noisy_sample_sizes) != 1:
        raise ValueError(f"Noise conditions have inconsistent sample sizes: {sorted(noisy_sample_sizes)}")
    noisy_n = next(iter(noisy_sample_sizes))
    legend_handles = [
        Line2D([0], [0], color=COLORS[metrics[0]], marker="o", label=METRICS[metrics[0]][1]),
        Line2D([0], [0], color=COLORS[metrics[1]], marker="o", label=METRICS[metrics[1]][1]),
    ]
    if ideal_n is not None:
        legend_handles.append(
            Line2D([0], [0], color=COLORS["baseline"], marker="D", linestyle="none", label="Ideal / no noise")
        )
    fig.legend(handles=legend_handles, loc="upper center", bbox_to_anchor=(0.5, 0.925), ncol=len(legend_handles), frameon=False, fontsize=8.7)
    fig.suptitle(title, fontsize=14, y=0.985)
    fig.subplots_adjust(left=0.08, right=0.99, top=0.84, bottom=0.11, wspace=0.18, hspace=0.34)
    return save_figure(fig, output_dir, stem, formats, dpi), noisy_n, ideal_n


def write_captions(output_dir: Path, hyper_n: int, noise_n: int, ideal_n: int | None) -> Path:
    ideal_clause = ""
    if ideal_n is not None:
        ideal_clause = f" The ideal/no-noise reference uses {ideal_n} independent runs."
    text = (
        "figureA_hyperparameter_sensitivity_traffic_3x3.png / .pdf\n"
        "Caption: QAOA hyperparameter sensitivity of traffic performance on the 3x3 grid at alpha=0.7. "
        f"Points indicate means across {hyper_n} independent simulation runs per condition; error bars denote "
        "95% confidence intervals across runs. Dashed vertical lines mark the baseline configuration.\n\n"
        "figureB_hyperparameter_sensitivity_quality_3x3.png / .pdf\n"
        "Caption: QAOA hyperparameter sensitivity of solution quality on the 3x3 grid at alpha=0.7. "
        f"Points indicate means across {hyper_n} independent simulation runs per condition; error bars denote "
        "95% confidence intervals across runs. Dashed vertical lines mark the baseline configuration.\n\n"
        "figureC_noise_sensitivity_traffic_3x3.png / .pdf\n"
        "Caption: QAOA synthetic-noise sensitivity of traffic performance on the 3x3 grid at alpha=0.7. "
        f"Noisy points indicate means across {noise_n} independent simulation runs per condition; error bars "
        f"denote 95% confidence intervals across runs, not individual QAOA decision epochs.{ideal_clause}\n\n"
        "figureD_noise_sensitivity_quality_3x3.png / .pdf\n"
        "Caption: QAOA synthetic-noise sensitivity of solution quality on the 3x3 grid at alpha=0.7. "
        f"Noisy points indicate means across {noise_n} independent simulation runs per condition; error bars "
        f"denote 95% confidence intervals across runs, not individual QAOA decision epochs.{ideal_clause}\n"
    )
    path = output_dir / "figure_captions.txt"
    path.write_text(text, encoding="utf-8")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--hyper-dir", type=Path, default=DEFAULT_HYPER_DIR)
    parser.add_argument("--noise-dir", type=Path, default=DEFAULT_NOISE_DIR)
    parser.add_argument("--ideal-data", type=Path, default=DEFAULT_IDEAL_DATA)
    parser.add_argument("--ideal-alpha-key", default="a7", help="Key for alpha=0.7 in the aggregate ideal JSON")
    parser.add_argument("--no-ideal-baseline", action="store_true", help="Omit the zero-noise reference")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--formats", nargs="+", choices=("png", "pdf", "svg"), default=["png", "pdf"])
    parser.add_argument("--dpi", type=int, default=300, help="PNG resolution (default: 300)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    grouped_hyper, baseline = load_hyperparameter_data(args.hyper_dir)
    grouped_noise = load_noise_data(args.noise_dir)
    ideal_data = None if args.no_ideal_baseline else args.ideal_data
    if ideal_data is not None and not ideal_data.is_file():
        raise ValueError(f"Ideal baseline file does not exist: {ideal_data}")

    created: list[Path] = []
    created += plot_hyperparameter_figure(
        grouped_hyper,
        baseline,
        ("travel", "waiting"),
        r"QAOA Hyperparameter Sensitivity — Traffic Performance (3×3 Grid, $\alpha=0.7$)",
        "figureA_hyperparameter_sensitivity_traffic_3x3",
        args.output_dir,
        args.formats,
        args.dpi,
    )
    created += plot_hyperparameter_figure(
        grouped_hyper,
        baseline,
        ("recovery", "gap"),
        r"QAOA Hyperparameter Sensitivity — Solution Quality (3×3 Grid, $\alpha=0.7$)",
        "figureB_hyperparameter_sensitivity_quality_3x3",
        args.output_dir,
        args.formats,
        args.dpi,
    )
    noise_traffic, noise_n, ideal_n = plot_noise_figure(
        grouped_noise,
        ideal_data,
        args.ideal_alpha_key,
        ("travel", "waiting"),
        r"QAOA Noise Sensitivity — Traffic Performance (3×3 Grid, $\alpha=0.7$)",
        "figureC_noise_sensitivity_traffic_3x3",
        args.output_dir,
        args.formats,
        args.dpi,
    )
    created += noise_traffic
    noise_quality, quality_noise_n, quality_ideal_n = plot_noise_figure(
        grouped_noise,
        ideal_data,
        args.ideal_alpha_key,
        ("recovery", "gap"),
        r"QAOA Noise Sensitivity — Solution Quality (3×3 Grid, $\alpha=0.7$)",
        "figureD_noise_sensitivity_quality_3x3",
        args.output_dir,
        args.formats,
        args.dpi,
    )
    if (quality_noise_n, quality_ideal_n) != (noise_n, ideal_n):
        raise ValueError("Traffic and solution-quality noise sample sizes do not match")
    created += noise_quality

    hyper_n = int(next(iter(grouped_hyper["beta"].values()))["experiment"]["num_runs_successful"])
    created.append(write_captions(args.output_dir, hyper_n, noise_n, ideal_n))
    print("Created:")
    for path in created:
        print(f"  {path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
