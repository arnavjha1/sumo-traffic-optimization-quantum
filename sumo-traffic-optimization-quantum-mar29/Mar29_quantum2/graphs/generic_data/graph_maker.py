"""Generate the standard traffic-performance graphs from experiment JSON files.

By default this recreates the format of throughput.py, travel_time.py, and
waiting_time.py for the 2x2 data set.  Use ``--save-dir`` for image files or
omit it to open the three matplotlib windows.
"""

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CLASSICAL_RESULTS = ROOT / "all_alpha_results.json"
DEFAULT_QUANTUM_RESULTS = ROOT / "quantum_data" / "quantum_simulation_results.json"

CONTROLLERS = {
    "fixed": ("Fixed-Time", "tab:blue"),
    "classical_local": ("Classical Optimization", "tab:green"),
    "mplight": ("MPLight", "tab:purple"),
    "presslight": ("PressLight", "tab:brown"),
}

METRICS = {
    "throughput": {
        "filename": "throughput.png",
        "ylabel": "Throughput",
        "title": "Throughput vs Probability of Straight (α)",
        "ylim": (300, 1200),
        "invert": False,
    },
    "average_travel_time": {
        "filename": "travel_time.png",
        "ylabel": "Average Travel Time (s)",
        "title": "Travel Time vs Probability of Straight (α)",
        "ylim": (50, 150),
        "invert": True,
    },
    "average_waiting_time": {
        "filename": "waiting_time.png",
        "ylabel": "Average Waiting Time (s)",
        "title": "Waiting Time vs Probability of Straight (α)",
        "ylim": (15, 70),
        "invert": True,
    },
}


def load_json(path):
    try:
        with path.open(encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError as error:
        raise SystemExit(f"Results file not found: {path}") from error
    except json.JSONDecodeError as error:
        raise SystemExit(f"Invalid JSON in {path}: {error}") from error


def load_classical_series(results, grid):
    try:
        grid_data = results["graph_data"][grid]
    except KeyError as error:
        available = ", ".join(results.get("graph_data", {}).keys()) or "none"
        raise SystemExit(f"Grid {grid!r} is unavailable (available: {available})") from error

    series = {}
    expected_alpha = None
    for controller in CONTROLLERS:
        try:
            points = sorted(grid_data[controller], key=lambda point: point["alpha_index"])
        except KeyError as error:
            raise SystemExit(f"Missing {grid}/{controller} graph data") from error

        alpha = np.asarray([point["alpha"] for point in points], dtype=float)
        if len(np.unique(alpha)) != len(alpha):
            raise SystemExit(f"Duplicate alpha values for {grid}/{controller}")
        if expected_alpha is None:
            expected_alpha = alpha
        elif not np.array_equal(alpha, expected_alpha):
            raise SystemExit(f"Alpha values for {grid}/{controller} do not match fixed")

        series[controller] = {
            metric: np.asarray([point[metric] for point in points], dtype=float)
            for metric in METRICS
        }
    return expected_alpha, series


def load_quantum_series(results, point_count):
    series = {metric: {field: [] for field in ("mean", "standard_deviation", "min", "max")}
              for metric in METRICS}
    for index in range(point_count):
        key = f"a{index}"
        try:
            statistics = results[key]["statistics"]
            for metric in METRICS:
                for field in series[metric]:
                    series[metric][field].append(statistics[metric][field])
        except KeyError as error:
            raise SystemExit(f"Missing quantum statistic {key}: {error}") from error

    return {
        metric: {field: np.asarray(values, dtype=float) for field, values in fields.items()}
        for metric, fields in series.items()
    }


def make_graph(alpha, classical, quantum, metric):
    config = METRICS[metric]
    figure, axes = plt.subplots()

    q = quantum[metric]
    quantum_color = "tab:red"
    axes.fill_between(alpha, q["min"], q["max"], color=quantum_color, alpha=0.08,
                      label="QAOA Optimization min-max")
    axes.fill_between(alpha, q["mean"] - 2 * q["standard_deviation"],
                      q["mean"] + 2 * q["standard_deviation"], color=quantum_color,
                      alpha=0.12, label="QAOA Optimization +/- 2 SD")
    axes.fill_between(alpha, q["mean"] - q["standard_deviation"],
                      q["mean"] + q["standard_deviation"], color=quantum_color,
                      alpha=0.22, label="QAOA Optimization +/- 1 SD")

    for controller, (label, color) in CONTROLLERS.items():
        values = classical[controller][metric]
        axes.plot(alpha, values, color=color, linewidth=2.5, label=label)
        axes.scatter(alpha, values, s=50, color=color)

    axes.plot(alpha, q["mean"], color=quantum_color, linewidth=2.5,
              label="QAOA Optimization")
    axes.scatter(alpha, q["mean"], s=50, color=quantum_color)
    axes.set_xlabel("Probability of Straight (α)")
    axes.set_ylabel(config["ylabel"])
    axes.set_title(config["title"])
    axes.set_ylim(*config["ylim"])
    if config["invert"]:
        axes.invert_yaxis()
    axes.legend()
    axes.grid()
    return figure


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--classical-results", type=Path, default=DEFAULT_CLASSICAL_RESULTS)
    parser.add_argument("--quantum-results", type=Path, default=DEFAULT_QUANTUM_RESULTS)
    parser.add_argument("--grid", default="2x2", help="graph_data grid to plot (default: 2x2)")
    parser.add_argument("--save-dir", type=Path, help="save PNGs here instead of opening windows")
    parser.add_argument("--dpi", type=int, default=150, help="saved-image DPI (default: 150)")
    return parser.parse_args()


def main():
    args = parse_args()
    classical_results = load_json(args.classical_results.resolve())
    quantum_results = load_json(args.quantum_results.resolve())
    alpha, classical = load_classical_series(classical_results, args.grid)
    quantum = load_quantum_series(quantum_results, len(alpha))

    figures = [(config["filename"], make_graph(alpha, classical, quantum, metric))
               for metric, config in METRICS.items()]
    if args.save_dir:
        args.save_dir.mkdir(parents=True, exist_ok=True)
        for filename, figure in figures:
            output = args.save_dir / filename
            figure.savefig(output, dpi=args.dpi, bbox_inches="tight")
            plt.close(figure)
            print(output.resolve())
    else:
        plt.show()


if __name__ == "__main__":
    main()
