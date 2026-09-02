#!/usr/bin/env python3
"""Generate the reviewer-oriented Results table set from saved experiments.

Outputs nine publication-ready LaTeX tables, a combined LaTeX file, and CSV
audit data.  No traffic simulation or optimizer is rerun.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any, Iterable

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "graphs" / "reviewer_results_tables"
ALPHA_RESULTS = ROOT / "all_alpha_results.json"
SEATTLE_RESULTS = ROOT / "all_seattle_results.json"
QAOA_ALPHA_PATHS = {
    "2x2": ROOT / "quantum_data" / "quantum_simulation_results.json",
    "3x3": ROOT / "quantum_data_3x3" / "quantum_3x3_simulation_results.json",
}
QAOA_SEATTLE_PATHS = {
    "2x2": ROOT / "seattle_2x2_quantum_data" / "quantum_2x2_seattle_results.json",
    "3x3": ROOT / "seattle_3x3_quantum_data" / "quantum_3x3_seattle_results_20runs.json",
}
HYPER_DIR = ROOT / "quantum_hyperparameter_data_3x3"
NOISE_DIR = ROOT / "quantum_noise_data_3x3"

TABLE_ORDER = (
    "fixed",
    "classical_local",
    "classical_global",
    "max_pressure",
    "scoot",
    "presslight",
    "mplight",
    "colight",
    "qaoa",
)
LABELS = {
    "fixed": "Fixed-Time",
    "classical_local": "Classical Local",
    "classical_global": "Classical Global",
    "max_pressure": "Max-Pressure",
    "scoot": "SCOOT",
    "presslight": "PressLight",
    "mplight": "MPLight",
    "colight": "CoLight",
    "qaoa": "QAOA",
}
METRICS = ("average_travel_time", "average_waiting_time", "throughput")
METRIC_LABELS = {
    "average_travel_time": "TT (s)",
    "average_waiting_time": "WT (s)",
    "throughput": "Throughput",
}
BENEFIT = {"average_travel_time": False, "average_waiting_time": False, "throughput": True}
SEATTLE_KEYS = {
    "average_travel_time": "average_travel_time",
    "average_waiting_time": "average_waiting_time",
    "throughput": "completed_vehicles",
}
REPRESENTATIVE_ALPHA = (0.5, 0.7, 1.0)
BOOTSTRAP_BASE_SEED = 20260901


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def alpha_key(alpha: float) -> str:
    return f"a{int(round(alpha * 10))}"


def deterministic_alpha_point(data: dict[str, Any], grid: str, controller: str, alpha: float) -> dict[str, Any]:
    matches = [
        point for point in data["graph_data"][grid][controller]
        if math.isclose(float(point["alpha"]), alpha)
    ]
    if len(matches) != 1:
        raise ValueError(f"Expected one {grid}/{controller}/alpha={alpha} point")
    return matches[0]


def qaoa_runs(data: dict[str, Any], alpha: float) -> list[dict[str, Any]]:
    runs = data[alpha_key(alpha)]["runs"]
    if len(runs) < 2:
        raise ValueError(f"At least two QAOA runs are required at alpha={alpha}")
    return runs


def bootstrap_mean(values: Iterable[float], rng: np.random.Generator, draws: int) -> tuple[float, float, float]:
    array = np.asarray(list(values), dtype=float)
    if len(array) < 2:
        raise ValueError("At least two values are required for a bootstrap CI")
    # Use the same resampling index matrix for every condition with the same n.
    # This keeps repeated presentations of one dataset numerically identical and
    # makes shifted QAOA-minus-exact intervals align with their descriptive CIs.
    del rng
    local_rng = np.random.default_rng(BOOTSTRAP_BASE_SEED + len(array) * 1_000_003 + draws)
    sampled = local_rng.choice(array, size=(draws, len(array)), replace=True).mean(axis=1)
    low, high = np.percentile(sampled, [2.5, 97.5])
    return float(array.mean()), float(low), float(high)


def hedges_g_one_sample(differences: Iterable[float]) -> float:
    values = np.asarray(list(differences), dtype=float)
    sd = float(np.std(values, ddof=1))
    if math.isclose(sd, 0.0):
        return math.copysign(math.inf, float(values.mean()))
    correction = 1.0 - 3.0 / (4.0 * len(values) - 5.0)
    return correction * float(values.mean()) / sd


def fmt_number(value: float, metric: str | None = None, decimals: int | None = None) -> str:
    if decimals is None:
        decimals = 0 if metric == "throughput" else 2
    return f"{value:.{decimals}f}"


def fmt_ci(mean: float, low: float, high: float, metric: str | None = None, decimals: int | None = None) -> str:
    return f"{fmt_number(mean, metric, decimals)} [{fmt_number(low, metric, decimals)}, {fmt_number(high, metric, decimals)}]"


def fmt_mean_sd(mean: float, sd: float, metric: str) -> str:
    return f"{fmt_number(mean, metric)} $\\pm$ {fmt_number(sd, metric)}"


def wrap_best(text: str, rank: int) -> str:
    if rank == 1:
        return rf"\textbf{{{text}}}"
    if rank == 2:
        return rf"\underline{{{text}}}"
    return text


def rank_map(values: dict[str, float], benefit: bool) -> dict[str, int]:
    ordered = sorted(values, key=values.get, reverse=benefit)
    return {key: index + 1 for index, key in enumerate(ordered)}


def table_environment(caption: str, label: str, columns: str, header: list[str], rows: list[str], *, resize: bool = False, scriptsize: bool = True) -> str:
    lines = [r"\begin{table*}[htbp]", r"\centering"]
    if scriptsize:
        lines += [r"\scriptsize", r"\setlength{\tabcolsep}{4pt}"]
    lines += [rf"\caption{{{caption}}}", rf"\label{{{label}}}"]
    if resize:
        lines.append(r"\resizebox{\textwidth}{!}{%")
    lines += [rf"\begin{{tabular}}{{{columns}}}", r"\toprule"]
    lines += header + [r"\midrule"] + rows + [r"\bottomrule", r"\end{tabular}"]
    if resize:
        lines.append(r"}")
    lines += [r"\end{table*}", ""]
    return "\n".join(lines)


def add_audit(audit: list[dict[str, Any]], table: int, **values: Any) -> None:
    audit.append({"table": table, **values})


def build_saturated_table(
    grid: str,
    table_number: int,
    alpha_data: dict[str, Any],
    qaoa_data: dict[str, Any],
    rng: np.random.Generator,
    draws: int,
    audit: list[dict[str, Any]],
) -> str:
    rows: list[str] = []
    for alpha_index, alpha in enumerate(REPRESENTATIVE_ALPHA):
        values: dict[str, dict[str, float]] = {metric: {} for metric in METRICS}
        displayed: dict[str, dict[str, str]] = {metric: {} for metric in METRICS}
        for controller in TABLE_ORDER:
            if controller == "qaoa":
                runs = qaoa_runs(qaoa_data, alpha)
                for metric in METRICS:
                    mean, low, high = bootstrap_mean((run[metric] for run in runs), rng, draws)
                    values[metric][controller] = mean
                    displayed[metric][controller] = fmt_ci(mean, low, high, metric)
                    add_audit(audit, table_number, grid=grid, condition=f"alpha={alpha:.1f}", item=LABELS[controller], metric=metric, value=mean, ci_low=low, ci_high=high, n=len(runs))
            else:
                point = deterministic_alpha_point(alpha_data, grid, controller, alpha)
                for metric in METRICS:
                    value = float(point[metric])
                    values[metric][controller] = value
                    displayed[metric][controller] = fmt_number(value, metric)
                    add_audit(audit, table_number, grid=grid, condition=f"alpha={alpha:.1f}", item=LABELS[controller], metric=metric, value=value, n=1)
        ranks = {metric: rank_map(values[metric], BENEFIT[metric]) for metric in METRICS}
        for controller in TABLE_ORDER:
            cells = [f"{alpha:.1f}", LABELS[controller]]
            for metric in METRICS:
                cells.append(wrap_best(displayed[metric][controller], 1 if ranks[metric][controller] == 1 else 0))
            rows.append(" & ".join(cells) + r" \\")
        if alpha_index < len(REPRESENTATIVE_ALPHA) - 1:
            rows.append(r"\addlinespace")
    caption = (
        rf"Saturated-traffic performance of all nine controllers on the ${grid[0]}\times{grid[2]}$ network at representative turning probabilities. "
        r"QAOA entries report mean [percentile-bootstrap 95\% CI] across 20 independent runs; other controllers are single deterministic runs. "
        r"Bold denotes the best observed value within each $\alpha$ block and metric."
    )
    return table_environment(
        caption,
        f"tab:saturated-{grid}-all-controller-summary",
        "rlrrr",
        [r"$\alpha$ & Controller & TT (s) & WT (s) & Throughput \\"],
        rows,
    )


def build_seattle_table(
    seattle: dict[str, Any],
    qaoa_seattle: dict[str, dict[str, Any]],
    audit: list[dict[str, Any]],
) -> str:
    rows: list[str] = []
    for grid_index, grid in enumerate(("2x2", "3x3")):
        values: dict[str, dict[str, float]] = {metric: {} for metric in METRICS}
        display: dict[str, dict[str, str]] = {metric: {} for metric in METRICS}
        for controller in TABLE_ORDER:
            if controller == "qaoa":
                stats = qaoa_seattle[grid]["overall_traffic_statistics"]
                for metric in METRICS:
                    key = SEATTLE_KEYS[metric]
                    mean = float(stats[key]["mean"])
                    sd = float(stats[key]["standard_deviation"])
                    values[metric][controller] = mean
                    display[metric][controller] = fmt_mean_sd(mean, sd, metric)
                    add_audit(audit, 3, grid=grid, condition="full-day", item=LABELS[controller], metric=metric, value=mean, standard_deviation=sd, n=int(stats[key]["count"]))
            else:
                overall = seattle["graph_data"][grid][controller]["overall"]
                for metric in METRICS:
                    value = float(overall[SEATTLE_KEYS[metric]])
                    values[metric][controller] = value
                    display[metric][controller] = fmt_number(value, metric)
                    add_audit(audit, 3, grid=grid, condition="full-day", item=LABELS[controller], metric=metric, value=value, n=1)
        ranks = {metric: rank_map(values[metric], BENEFIT[metric]) for metric in METRICS}
        for controller in TABLE_ORDER:
            cells = [grid, LABELS[controller]]
            for metric in METRICS:
                cells.append(wrap_best(display[metric][controller], 1 if ranks[metric][controller] == 1 else 0))
            rows.append(" & ".join(cells) + r" \\")
        if grid_index == 0:
            rows.append(r"\addlinespace")
    caption = (
        r"Full-day Seattle performance for all nine controllers on both networks. QAOA entries report mean $\pm$ standard deviation across 20 independent runs; "
        r"other controllers are single deterministic runs. Completed vehicles is retained as the Seattle throughput measure. Bold denotes the best observed value within each network and metric."
    )
    return table_environment(
        caption,
        "tab:seattle-24h-all-controller-summary",
        "llrrr",
        [r"Grid & Controller & Full-day TT (s) & Full-day WT (s) & Completed Vehicles \\"],
        rows,
    )


def build_qaoa_descriptive_table(
    qaoa_alpha_data: dict[str, dict[str, Any]],
    rng: np.random.Generator,
    draws: int,
    audit: list[dict[str, Any]],
) -> str:
    rows: list[str] = []
    for grid in ("2x2", "3x3"):
        for alpha in REPRESENTATIVE_ALPHA:
            runs = qaoa_runs(qaoa_alpha_data[grid], alpha)
            for metric in METRICS:
                values = np.asarray([float(run[metric]) for run in runs])
                mean, low, high = bootstrap_mean(values, rng, draws)
                sd = float(values.std(ddof=1))
                rows.append(" & ".join([
                    grid,
                    f"{alpha:.1f}",
                    METRIC_LABELS[metric],
                    fmt_number(mean, metric),
                    fmt_number(sd, metric),
                    f"[{fmt_number(low, metric)}, {fmt_number(high, metric)}]",
                    fmt_number(float(values.min()), metric),
                    fmt_number(float(values.max()), metric),
                ]) + r" \\")
                add_audit(audit, 4, grid=grid, condition=f"alpha={alpha:.1f}", item="QAOA", metric=metric, value=mean, standard_deviation=sd, ci_low=low, ci_high=high, minimum=float(values.min()), maximum=float(values.max()), n=len(values))
        if grid == "2x2":
            rows.append(r"\addlinespace")
    return table_environment(
        r"Repeated-run descriptive statistics for QAOA at representative saturated-traffic conditions. Confidence intervals are percentile-bootstrap 95\% intervals from 10,000 resamples of the 20 independent runs.",
        "tab:qaoa-repeated-run-descriptive-statistics",
        "llrrrrrr",
        [r"Grid & $\alpha$ & Metric & Mean & SD & Bootstrap 95\% CI & Min & Max \\"],
        rows,
        resize=True,
    )


def build_qaoa_exact_comparison_table(
    alpha_data: dict[str, Any],
    qaoa_alpha_data: dict[str, dict[str, Any]],
    seattle: dict[str, Any],
    qaoa_seattle: dict[str, dict[str, Any]],
    rng: np.random.Generator,
    draws: int,
    audit: list[dict[str, Any]],
) -> str:
    rows: list[str] = []

    def append_condition(grid: str, condition: str, metric: str, qaoa_values: np.ndarray, exact_value: float) -> None:
        differences = qaoa_values - exact_value
        q_mean = float(qaoa_values.mean())
        diff_mean, low, high = bootstrap_mean(differences, rng, draws)
        g = hedges_g_one_sample(differences)
        g_text = r"$\infty$" if math.isinf(g) else f"{g:.2f}"
        rows.append(" & ".join([
            grid,
            condition,
            METRIC_LABELS[metric],
            fmt_number(q_mean, metric),
            fmt_number(exact_value, metric),
            fmt_number(diff_mean, metric),
            f"[{fmt_number(low, metric)}, {fmt_number(high, metric)}]",
            g_text,
        ]) + r" \\")
        add_audit(audit, 5, grid=grid, condition=condition, item="QAOA - Exact Classical Global", metric=metric, value=diff_mean, qaoa_mean=q_mean, exact_global=exact_value, ci_low=low, ci_high=high, hedges_g=g, n=len(qaoa_values))

    for grid in ("2x2", "3x3"):
        for alpha in REPRESENTATIVE_ALPHA:
            runs = qaoa_runs(qaoa_alpha_data[grid], alpha)
            for metric in METRICS:
                exact = float(deterministic_alpha_point(alpha_data, grid, "classical_global", alpha)[metric])
                append_condition(grid, rf"$\alpha={alpha:.1f}$", metric, np.asarray([float(run[metric]) for run in runs]), exact)
        rows.append(r"\addlinespace")
    for grid in ("2x2", "3x3"):
        exact_overall = seattle["graph_data"][grid]["classical_global"]["overall"]
        runs = qaoa_seattle[grid]["runs"]
        for metric in METRICS:
            key = SEATTLE_KEYS[metric]
            append_condition(grid, "Seattle full day", metric, np.asarray([float(run["overall_traffic"][key]) for run in runs]), float(exact_overall[key]))
        if grid == "2x2":
            rows.append(r"\addlinespace")
    caption = (
        r"QAOA compared directly with the exact Classical Global controller. Difference is QAOA minus Exact Classical Global in the metric's native units; therefore negative TT/WT differences and positive throughput differences favor QAOA. "
        r"Intervals are percentile-bootstrap 95\% CIs from 10,000 resamples, and effect size is one-sample Hedges' $g$ relative to the deterministic exact-global benchmark ($n=20$ QAOA runs per condition)."
    )
    return table_environment(
        caption,
        "tab:qaoa-vs-exact-global-bootstrap-comparison",
        "lllrrrrr",
        [r"Grid & Condition & Metric & QAOA Mean & Exact Global & Difference & Bootstrap 95\% CI & Hedges' $g$ \\"],
        rows,
        resize=True,
    )


def build_exact_quality_table(
    qaoa_alpha_data: dict[str, dict[str, Any]],
    rng: np.random.Generator,
    draws: int,
    audit: list[dict[str, Any]],
) -> str:
    rows: list[str] = []
    configurations = {"2x2": 16, "3x3": 512}
    alpha = 0.7
    for grid in ("2x2", "3x3"):
        entry = qaoa_alpha_data[grid][alpha_key(alpha)]
        runs = entry["runs"]
        stats = entry["statistics"]
        recovery = np.asarray([float(run["optimum_recovery_rate"]) for run in runs])
        recovery_mean, recovery_low, recovery_high = bootstrap_mean(recovery, rng, draws)
        exact_energy = float(stats["average_exact_min_energy"]["mean"])
        qaoa_energy = float(stats["average_selected_energy"]["mean"])
        gap_mean = float(stats["average_optimality_gap"]["mean"])
        gap_median = float(stats["average_optimality_gap"]["median"])
        rows.append(" & ".join([
            grid,
            str(configurations[grid]),
            f"{exact_energy:.3f}",
            f"{qaoa_energy:.3f}",
            f"{gap_mean:.3f}",
            f"{gap_median:.3f}",
            f"{100.0 * recovery_mean:.2f}\\%",
            f"[{100.0 * recovery_low:.2f}\\%, {100.0 * recovery_high:.2f}\\%]",
        ]) + r" \\")
        add_audit(audit, 6, grid=grid, condition="alpha=0.7", item="QAOA optimization quality", metric="average_exact_min_energy", value=exact_energy, n=len(runs))
        add_audit(audit, 6, grid=grid, condition="alpha=0.7", item="QAOA optimization quality", metric="average_selected_energy", value=qaoa_energy, n=len(runs))
        add_audit(audit, 6, grid=grid, condition="alpha=0.7", item="QAOA optimization quality", metric="average_optimality_gap", value=gap_mean, median=gap_median, n=len(runs))
        add_audit(audit, 6, grid=grid, condition="alpha=0.7", item="QAOA optimization quality", metric="optimum_recovery_rate", value=recovery_mean, ci_low=recovery_low, ci_high=recovery_high, n=len(runs))
    caption = (
        r"Exact-search and QAOA solution quality at $\alpha=0.7$. Because the traffic state and Hamiltonian change during a simulation, exact minimum and QAOA energies are means of the run-level decision-averaged energies, not one fixed Hamiltonian value. "
        r"The gap median is the median of run-level average gaps. Recovery intervals are percentile-bootstrap 95\% CIs across 20 independent runs."
    )
    return table_environment(
        caption,
        "tab:qaoa-exact-optimization-quality",
        "lrrrrrrr",
        [r"Grid & Exact Configurations & Mean Exact Min. Energy & Mean QAOA Energy & Mean Gap & Median Gap & Recovery & Bootstrap 95\% CI \\"],
        rows,
        resize=True,
    )


def stat_ci_cell(result: dict[str, Any], metric: str, *, percent: bool = False, decimals: int = 2) -> str:
    stat = result["statistics"][metric]
    if percent:
        mean = 100.0 * float(stat["mean"])
        low = 100.0 * float(stat["ci95_low"])
        high = 100.0 * float(stat["ci95_high"])
        return f"{mean:.{decimals}f}\\% [{low:.{decimals}f}\\%, {high:.{decimals}f}\\%]"
    return fmt_ci(float(stat["mean"]), float(stat["ci95_low"]), float(stat["ci95_high"]), decimals=decimals)


def hyper_value_label(parameter: str, value: float) -> str:
    if parameter == "gamma":
        known = ((4 * math.pi / 9, r"$4\pi/9$"), (7 * math.pi / 9, r"$7\pi/9$"), (math.pi, r"$\pi$"))
        for expected, label in known:
            if abs(value - expected) < 0.002:
                return label
    if parameter == "beta":
        known = ((math.pi / 9, r"$\pi/9$"), (math.pi / 6, r"$\pi/6$"), (5 * math.pi / 18, r"$5\pi/18$"))
        for expected, label in known:
            if abs(value - expected) < 0.002:
                return label
    if parameter in {"p", "shots"}:
        return str(int(round(value)))
    return f"{value:.3f}"


def load_condition_results(directory: Path, pattern: str, skip_all_levels: bool = False) -> list[dict[str, Any]]:
    paths = sorted(directory.glob(pattern))
    if skip_all_levels:
        paths = [path for path in paths if "_all_levels_" not in path.name]
    return [load_json(path) for path in paths]


def build_hyperparameter_table(results: list[dict[str, Any]], audit: list[dict[str, Any]]) -> str:
    order = {"gamma": 0, "beta": 1, "p": 2, "shots": 3}
    results = sorted(results, key=lambda result: (order[result["experiment"]["hyperparameter"]], float(result["experiment"]["hyperparameter_value"])))
    rows: list[str] = []
    previous = None
    for result in results:
        exp = result["experiment"]
        parameter = exp["hyperparameter"]
        if previous is not None and parameter != previous:
            rows.append(r"\addlinespace")
        previous = parameter
        value = float(exp["hyperparameter_value"])
        parameter_label = {"gamma": r"$\gamma$", "beta": r"$\beta$", "p": r"$p$", "shots": "Shots"}[parameter]
        cells = [
            parameter_label,
            hyper_value_label(parameter, value),
            stat_ci_cell(result, "average_travel_time"),
            stat_ci_cell(result, "average_waiting_time"),
            stat_ci_cell(result, "throughput", decimals=1),
            stat_ci_cell(result, "average_optimality_gap", decimals=3),
            stat_ci_cell(result, "optimum_recovery_rate", percent=True),
        ]
        rows.append(" & ".join(cells) + r" \\")
        for metric in ("average_travel_time", "average_waiting_time", "throughput", "average_optimality_gap", "optimum_recovery_rate"):
            stat = result["statistics"][metric]
            add_audit(audit, 7, grid="3x3", condition="alpha=0.7", item=parameter, level=value, metric=metric, value=float(stat["mean"]), ci_low=float(stat["ci95_low"]), ci_high=float(stat["ci95_high"]), n=int(exp["num_runs_successful"]))
    caption = (
        r"QAOA hyperparameter sensitivity on the $3\times3$ network at $\alpha=0.7$. Each cell reports mean [95\% CI] across 10 independent runs; intervals are the stored two-sided Student-$t$ confidence intervals across runs. "
        r"Only the listed parameter changes within each block; the baseline is $\gamma=\pi$, $\beta=\pi/6$, $p=2$, and 512 shots. Recovery is reported as a percentage."
    )
    return table_environment(
        caption,
        "tab:qaoa-hyperparameter-sensitivity-summary",
        "llrrrrr",
        [r"Parameter & Value & TT (s) & WT (s) & Throughput & Mean Gap & Recovery \\"],
        rows,
        resize=True,
    )


def noise_level_label(noise_type: str, level: float) -> str:
    if noise_type == "angle":
        return f"{level:.3f} rad"
    return f"{100.0 * level:g}\\%"


def build_noise_table(
    results: list[dict[str, Any]],
    ideal: dict[str, Any],
    audit: list[dict[str, Any]],
) -> str:
    rows: list[str] = []
    ideal_wrapper = {"statistics": ideal["statistics"]}
    rows.append(" & ".join([
        "Ideal / no noise", "--",
        stat_ci_cell(ideal_wrapper, "average_travel_time"),
        stat_ci_cell(ideal_wrapper, "average_waiting_time"),
        stat_ci_cell(ideal_wrapper, "throughput", decimals=1),
        stat_ci_cell(ideal_wrapper, "average_optimality_gap", decimals=3),
        stat_ci_cell(ideal_wrapper, "optimum_recovery_rate", percent=True),
    ]) + r" \\")
    for metric in ("average_travel_time", "average_waiting_time", "throughput", "average_optimality_gap", "optimum_recovery_rate"):
        stat = ideal["statistics"][metric]
        # The aggregate files contain SE but not explicit CI fields; use the raw runs for the audit record only.
        add_audit(audit, 8, grid="3x3", condition="alpha=0.7", item="Ideal / no noise", level=0.0, metric=metric, value=float(stat["mean"]), n=int(ideal["num_runs_successful"]))
    rows.append(r"\addlinespace")

    order = {"angle": 0, "depolarizing": 1, "readout": 2}
    results = sorted(results, key=lambda result: (order[result["experiment"]["noise_type"]], float(result["experiment"]["noise_level"])))
    previous = None
    for result in results:
        exp = result["experiment"]
        noise_type = exp["noise_type"]
        if previous is not None and noise_type != previous:
            rows.append(r"\addlinespace")
        previous = noise_type
        level = float(exp["noise_level"])
        label = {"angle": "Angle perturbation", "depolarizing": "Depolarizing", "readout": "Readout"}[noise_type]
        rows.append(" & ".join([
            label,
            noise_level_label(noise_type, level),
            stat_ci_cell(result, "average_travel_time"),
            stat_ci_cell(result, "average_waiting_time"),
            stat_ci_cell(result, "throughput", decimals=1),
            stat_ci_cell(result, "average_optimality_gap", decimals=3),
            stat_ci_cell(result, "optimum_recovery_rate", percent=True),
        ]) + r" \\")
        for metric in ("average_travel_time", "average_waiting_time", "throughput", "average_optimality_gap", "optimum_recovery_rate"):
            stat = result["statistics"][metric]
            add_audit(audit, 8, grid="3x3", condition="alpha=0.7", item=label, level=level, metric=metric, value=float(stat["mean"]), ci_low=float(stat["ci95_low"]), ci_high=float(stat["ci95_high"]), n=int(exp["num_runs_successful"]))
    caption = (
        r"QAOA synthetic-noise sensitivity on the $3\times3$ network at $\alpha=0.7$. Each cell reports mean [95\% CI]. Noisy conditions use 10 independent runs and stored Student-$t$ intervals; the ideal reference uses 20 independent runs and its corresponding two-sided Student-$t$ interval. "
        r"Angle levels are Gaussian perturbation standard deviations; depolarizing and readout levels are probabilities. Recovery is reported as a percentage."
    )
    return table_environment(
        caption,
        "tab:qaoa-quantum-noise-sensitivity-summary",
        "llrrrrr",
        [r"Noise Mechanism & Level & TT (s) & WT (s) & Throughput & Mean Gap & Recovery \\"],
        rows,
        resize=True,
    )


def add_t_ci_fields(entry: dict[str, Any]) -> dict[str, Any]:
    """Add 95% t-interval fields to aggregate stats for table-cell reuse."""
    # Critical values for df=19; aggregate QAOA alpha conditions have n=20.
    critical = 2.093024054
    copied = {"statistics": {}}
    for metric, stat in entry["statistics"].items():
        if not isinstance(stat, dict) or "mean" not in stat:
            copied["statistics"][metric] = stat
            continue
        current = dict(stat)
        if "ci95_low" not in current:
            half = critical * float(current["standard_error"])
            current["ci95_low"] = float(current["mean"]) - half
            current["ci95_high"] = float(current["mean"]) + half
        copied["statistics"][metric] = current
    return copied


def build_ranking_table(
    alpha_data: dict[str, Any],
    qaoa_alpha_data: dict[str, dict[str, Any]],
    seattle: dict[str, Any],
    qaoa_seattle: dict[str, dict[str, Any]],
    audit: list[dict[str, Any]],
) -> str:
    alpha = 0.7
    columns: list[tuple[str, str, str]] = []
    for grid in ("2x2", "3x3"):
        for metric in METRICS:
            columns.append((grid, f"alpha={alpha:.1f}", metric))
    for metric in METRICS:
        columns.append(("3x3", "Seattle full-day", metric))

    values: dict[tuple[str, str, str], dict[str, float]] = {column: {} for column in columns}
    for controller in TABLE_ORDER:
        for grid in ("2x2", "3x3"):
            if controller == "qaoa":
                for metric in METRICS:
                    values[(grid, f"alpha={alpha:.1f}", metric)][controller] = float(qaoa_alpha_data[grid][alpha_key(alpha)]["statistics"][metric]["mean"])
            else:
                point = deterministic_alpha_point(alpha_data, grid, controller, alpha)
                for metric in METRICS:
                    values[(grid, f"alpha={alpha:.1f}", metric)][controller] = float(point[metric])
        if controller == "qaoa":
            stats = qaoa_seattle["3x3"]["overall_traffic_statistics"]
            for metric in METRICS:
                values[("3x3", "Seattle full-day", metric)][controller] = float(stats[SEATTLE_KEYS[metric]]["mean"])
        else:
            overall = seattle["graph_data"]["3x3"][controller]["overall"]
            for metric in METRICS:
                values[("3x3", "Seattle full-day", metric)][controller] = float(overall[SEATTLE_KEYS[metric]])

    ranks = {column: rank_map(values[column], BENEFIT[column[2]]) for column in columns}
    rows: list[str] = []
    for controller in TABLE_ORDER:
        cells = [LABELS[controller]]
        for column in columns:
            metric = column[2]
            value = values[column][controller]
            cells.append(wrap_best(fmt_number(value, metric), ranks[column][controller]))
            add_audit(audit, 9, grid=column[0], condition=column[1], item=LABELS[controller], metric=metric, value=value, rank=ranks[column][controller], n=20 if controller == "qaoa" else 1)
        rows.append(" & ".join(cells) + r" \\")
    header = [
        r"& \multicolumn{3}{c}{$2\times2$, $\alpha=0.7$} & \multicolumn{3}{c}{$3\times3$, $\alpha=0.7$} & \multicolumn{3}{c}{Seattle $3\times3$ full day} \\",
        r"\cmidrule(lr){2-4}\cmidrule(lr){5-7}\cmidrule(lr){8-10}",
        r"Controller & TT & WT & TP & TT & WT & TP & TT & WT & Completed \\",
    ]
    caption = (
        r"Compact benchmark ranking across the representative saturated condition and the Seattle $3\times3$ case study. QAOA values are means across 20 independent runs; other values are single deterministic runs. "
        r"Within each column, the best value is bold and the second-best is underlined. TT and WT are cost metrics; TP/completed vehicles are benefit metrics."
    )
    return table_environment(caption, "tab:overall-controller-benchmark-ranking", "lrrrrrrrrr", header, rows, resize=True)


def write_audit_csv(path: Path, audit: list[dict[str, Any]]) -> None:
    fields: list[str] = []
    for row in audit:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(audit)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--bootstrap-draws", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20260901)
    return parser.parse_args()


def main() -> int:
    global BOOTSTRAP_BASE_SEED
    args = parse_args()
    BOOTSTRAP_BASE_SEED = args.seed
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(args.seed)
    alpha_data = load_json(ALPHA_RESULTS)
    seattle = load_json(SEATTLE_RESULTS)
    qaoa_alpha_data = {grid: load_json(path) for grid, path in QAOA_ALPHA_PATHS.items()}
    qaoa_seattle = {grid: load_json(path) for grid, path in QAOA_SEATTLE_PATHS.items()}
    hyper_results = load_condition_results(HYPER_DIR, "*_value*_results.json")
    noise_results = load_condition_results(NOISE_DIR, "*_results.json", skip_all_levels=True)
    ideal = qaoa_alpha_data["3x3"]["a7"]
    ideal_with_ci = dict(ideal)
    ideal_with_ci["statistics"] = add_t_ci_fields(ideal)["statistics"]

    audit: list[dict[str, Any]] = []
    tables = [
        build_saturated_table("2x2", 1, alpha_data, qaoa_alpha_data["2x2"], rng, args.bootstrap_draws, audit),
        build_saturated_table("3x3", 2, alpha_data, qaoa_alpha_data["3x3"], rng, args.bootstrap_draws, audit),
        build_seattle_table(seattle, qaoa_seattle, audit),
        build_qaoa_descriptive_table(qaoa_alpha_data, rng, args.bootstrap_draws, audit),
        build_qaoa_exact_comparison_table(alpha_data, qaoa_alpha_data, seattle, qaoa_seattle, rng, args.bootstrap_draws, audit),
        build_exact_quality_table(qaoa_alpha_data, rng, args.bootstrap_draws, audit),
        build_hyperparameter_table(hyper_results, audit),
        build_noise_table(noise_results, ideal_with_ci, audit),
        build_ranking_table(alpha_data, qaoa_alpha_data, seattle, qaoa_seattle, audit),
    ]
    filenames = [
        "table01_saturated_2x2.tex",
        "table02_saturated_3x3.tex",
        "table03_seattle_24h_summary.tex",
        "table04_qaoa_repeated_run_statistics.tex",
        "table05_qaoa_vs_exact_global.tex",
        "table06_exact_optimization_quality.tex",
        "table07_hyperparameter_sensitivity.tex",
        "table08_quantum_noise_sensitivity.tex",
        "table09_overall_controller_ranking.tex",
    ]
    created: list[Path] = []
    for filename, table in zip(filenames, tables):
        path = args.output_dir / filename
        path.write_text(table, encoding="utf-8")
        created.append(path)
    combined = args.output_dir / "reviewer_results_tables_all.tex"
    combined.write_text("\n\n".join(f"% Table {index}\n{table}" for index, table in enumerate(tables, 1)), encoding="utf-8")
    created.append(combined)
    audit_path = args.output_dir / "reviewer_results_tables_audit_data.csv"
    write_audit_csv(audit_path, audit)
    created.append(audit_path)
    requirements = args.output_dir / "latex_requirements.txt"
    requirements.write_text(
        "Required packages: booktabs, graphicx.\n"
        "Recommended preamble: \\usepackage{booktabs} and \\usepackage{graphicx}.\n"
        "All files are table environments and can be inserted directly into the manuscript.\n",
        encoding="utf-8",
    )
    created.append(requirements)
    print("Created:")
    for path in created:
        print(f"  {path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
