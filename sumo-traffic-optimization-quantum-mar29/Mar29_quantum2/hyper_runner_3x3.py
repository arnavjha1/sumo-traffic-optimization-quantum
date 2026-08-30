import argparse
import json
import math
import re
import statistics
import subprocess
import sys
from pathlib import Path


# =============================
# CONFIG
# =============================

NUM_RUNS = 10
ALPHA_INDEX = 7

BASE_DIR = Path(__file__).parent
QUANTUM_DIR = BASE_DIR / "grid_3x3/3_quantum"

HYPER_FILE = QUANTUM_DIR / "a7_hyper.py"

OUTPUT_DIR = BASE_DIR / "quantum_hyperparameter_data_3x3"
OUTPUT_DIR.mkdir(exist_ok=True)


# Baseline QAOA configuration used by the sensitivity study.
BASE_GAMMA = math.pi
BASE_BETA = math.pi / 6
BASE_P = 2
BASE_SHOTS = 512


# One-at-a-time hyperparameter sensitivity values.
#
# The baseline configuration is run separately once.
# Each parameter sweep therefore contains only the two
# non-baseline values.
HYPER_VALUES = {
    "gamma": {
        "value1": 1.396,
        "value2": 2.443,
        "value3": math.pi,
    },

    "beta": {
        "value1": 0.349,
        "value2": math.pi / 6,
        "value3": 0.873,
    },

    "p": {
        "value1": 1,
        "value2": 2,
        "value3": 3,
    },

    "shots": {
        "value1": 200,
        "value2": 512,
        "value3": 1000,
    },
}

# Ten distinct reproducible replicate seeds.
SEEDS = [1001 + i for i in range(NUM_RUNS)]

# =============================
# COMMAND LINE
# =============================

def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Run 3x3 QAOA hyperparameter sensitivity experiments. "
            "Choose gamma, beta, p, shots, or all."
        )
    )

    parser.add_argument(
        "hyper_type",
        choices=["gamma", "beta", "p", "shots", "all"],
        help="Hyperparameter experiment to run."
    )

    return parser.parse_args()


# =============================
# PARSING
# =============================

def extract_metrics(output):
    travel_match = re.search(
        r"Average Travel Time:\s*([\d.]+)\s*s",
        output
    )

    waiting_match = re.search(
        r"Average Waiting Time:\s*([\d.]+)\s*s",
        output
    )

    throughput_match = re.search(
        r"Throughput:\s*(\d+)",
        output
    )

    inserted_match = re.search(
        r"Vehicles inserted:\s*(\d+)",
        output
    )

    remaining_match = re.search(
        r"Vehicles still in network at t=\d+:\s*(\d+)",
        output
    )

    energy_match = re.search(
        r"ENERGY_JSON:\s*(\{.*\})",
        output
    )

    if (
        not travel_match
        or not waiting_match
        or not throughput_match
        or not inserted_match
        or not remaining_match
        or not energy_match
    ):
        raise ValueError(
            "Could not parse traffic metrics or ENERGY_JSON."
        )

    energy_metrics = json.loads(energy_match.group(1))

    return {
        "throughput": int(throughput_match.group(1)),
        "average_waiting_time": float(waiting_match.group(1)),
        "average_travel_time": float(travel_match.group(1)),
        "vehicles_inserted": int(inserted_match.group(1)),
        "vehicles_remaining": int(remaining_match.group(1)),
        **energy_metrics,
    }


# =============================
# STATS
# =============================

def calculate_stats(values):
    if len(values) == 0:
        return {}

    if len(values) == 1:
        return {
            "mean": values[0],
            "median": values[0],
            "min": values[0],
            "max": values[0],
            "standard_deviation": 0,
            "variance": 0,
            "standard_error": 0,
            "ci95_low": values[0],
            "ci95_high": values[0],
        }

    stdev = statistics.stdev(values)
    standard_error = stdev / math.sqrt(len(values))

    # Student-t critical value for n=10 (df=9), which is the fixed
    # replicate count in this experiment.
    if len(values) == 10:
        critical = 2.262157
    else:
        # Normal approximation fallback if NUM_RUNS is later changed.
        critical = 1.96

    mean_value = statistics.mean(values)
    margin = critical * standard_error

    return {
        "mean": mean_value,
        "median": statistics.median(values),
        "min": min(values),
        "max": max(values),
        "standard_deviation": stdev,
        "variance": statistics.variance(values),
        "standard_error": standard_error,
        "ci95_low": mean_value - margin,
        "ci95_high": mean_value + margin,
    }


def summarize_runs(runs):
    successful_runs = [run for run in runs if "error" not in run]

    fields = [
        "throughput",
        "average_waiting_time",
        "average_travel_time",
        "vehicles_inserted",
        "vehicles_remaining",
        "average_selected_energy",
        "average_exact_min_energy",
        "average_optimality_gap",
        "maximum_optimality_gap",
        "optimum_recovery_rate",
        "average_energy_reduction",
    ]

    statistics_by_metric = {}

    for field in fields:
        values = [run[field] for run in successful_runs]
        statistics_by_metric[field] = calculate_stats(values)

    return successful_runs, statistics_by_metric


# =============================
# SAVE HELPERS
# =============================

def result_paths(hyper_type, condition_name):
    stem = f"{hyper_type}_{condition_name}"

    return (
        OUTPUT_DIR / f"{stem}_results.json",
        OUTPUT_DIR / f"{stem}_summary.txt",
    )


def write_condition_results(
    hyper_type,
    condition_name,
    hyper_value,
    runs
):
    successful_runs, stats = summarize_runs(runs)

    json_path, txt_path = result_paths(
        hyper_type,
        condition_name
    )

    result_data = {
        "experiment": {
            "network": "3x3",
            "alpha_index": ALPHA_INDEX,
            "alpha": 0.7,
            "hyperparameter": hyper_type,
            "condition_name": condition_name,
            "hyperparameter_value": hyper_value,
            "num_runs_attempted": len(runs),
            "num_runs_target": NUM_RUNS,
            "num_runs_successful": len(successful_runs),
            "seeds": SEEDS,
            "source_file": str(HYPER_FILE),
            "baseline_configuration": {
                "gamma": BASE_GAMMA,
                "beta": BASE_BETA,
                "p": BASE_P,
                "shots": BASE_SHOTS,
            },
        },

        "runs": runs,
        "statistics": stats,
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result_data, f, indent=4)

    with open(txt_path, "w", encoding="utf-8") as f:

        f.write(
            "===== 3x3 QAOA HYPERPARAMETER "
            "SENSITIVITY SUMMARY =====\n\n"
        )

        f.write(f"Hyperparameter: {hyper_type}\n")
        f.write(f"Condition: {condition_name}\n")
        f.write(f"Test value: {hyper_value}\n")

        f.write(
            f"Runs attempted: "
            f"{len(runs)}/{NUM_RUNS}\n"
        )

        f.write(
            f"Runs successful: "
            f"{len(successful_runs)}/{NUM_RUNS}\n\n"
        )

        f.write(
            "Baseline configuration:\n"
            f"  gamma = {BASE_GAMMA}\n"
            f"  beta = {BASE_BETA}\n"
            f"  p = {BASE_P}\n"
            f"  shots = {BASE_SHOTS}\n\n"
        )

        for metric_name, metric_stats in stats.items():

            f.write(f"{metric_name}:\n")

            f.write(
                json.dumps(
                    metric_stats,
                    indent=4
                )
            )

            f.write("\n\n")

    return (
        json_path,
        txt_path,
        successful_runs,
        stats
    )


# =============================
# RUN CONDITION
# =============================

def run_condition(
    hyper_type,
    condition_name,
    hyper_value
):

    print(
        f"\n===== "
        f"{hyper_type.upper()} — "
        f"{condition_name.upper()} "
        f"({hyper_value}) ====="
    )

    runs = []

    for run_number in range(1, NUM_RUNS + 1):

        seed = SEEDS[run_number - 1]

        print(
            f"{hyper_type}/{condition_name}: "
            f"Run {run_number}/{NUM_RUNS} "
            f"(seed={seed})"
        )

        output = ""

        try:

            command = [
                sys.executable,
                str(HYPER_FILE),
                str(ALPHA_INDEX),
                hyper_type,
                str(hyper_value),
                str(seed),
            ]

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                cwd=BASE_DIR,
                timeout=7200,
            )

            output = result.stdout

            if result.returncode != 0:

                raise subprocess.CalledProcessError(
                    result.returncode,
                    result.args,
                    output=result.stdout,
                    stderr=result.stderr,
                )

            metrics = extract_metrics(output)

            runs.append({
                "run": run_number,
                "seed": seed,

                "hyperparameter": hyper_type,
                "condition_name": condition_name,
                "hyperparameter_value": hyper_value,

                "throughput":
                    metrics["throughput"],

                "average_waiting_time":
                    metrics["average_waiting_time"],

                "average_travel_time":
                    metrics["average_travel_time"],

                "vehicles_inserted":
                    metrics["vehicles_inserted"],

                "vehicles_remaining":
                    metrics["vehicles_remaining"],

                "shots":
                    metrics["shots"],

                "num_decisions":
                    metrics["num_decisions"],

                "optimal_hits":
                    metrics["optimal_hits"],

                "optimum_recovery_rate":
                    metrics["optimum_recovery_rate"],

                "average_selected_energy":
                    metrics["average_selected_energy"],

                "average_exact_min_energy":
                    metrics["average_exact_min_energy"],

                "average_optimality_gap":
                    metrics["average_optimality_gap"],

                "maximum_optimality_gap":
                    metrics["maximum_optimality_gap"],

                "average_energy_reduction":
                    metrics["average_energy_reduction"],

                "raw_output": output,
            })

        except subprocess.TimeoutExpired:

            runs.append({
                "run": run_number,
                "seed": seed,
                "hyperparameter": hyper_type,
                "condition_name": condition_name,
                "hyperparameter_value": hyper_value,
                "error": "Timeout (>2 hours)",
            })

        except subprocess.CalledProcessError as e:

            runs.append({
                "run": run_number,
                "seed": seed,
                "hyperparameter": hyper_type,
                "condition_name": condition_name,
                "hyperparameter_value": hyper_value,
                "error": "Simulation failed",
                "details": str(e),
                "stderr": e.stderr,
                "raw_output": e.output,
            })

        except ValueError as e:

            runs.append({
                "run": run_number,
                "seed": seed,
                "hyperparameter": hyper_type,
                "condition_name": condition_name,
                "hyperparameter_value": hyper_value,
                "error": "Parsing failed",
                "details": str(e),
                "raw_output": output,
            })

        # Save after every replicate.
        (
            json_path,
            txt_path,
            successful_runs,
            stats
        ) = write_condition_results(
            hyper_type,
            condition_name,
            hyper_value,
            runs
        )

        heartbeat_path = (
            OUTPUT_DIR
            / "hyperparameter_heartbeat.txt"
        )

        with open(
            heartbeat_path,
            "w",
            encoding="utf-8"
        ) as f:

            f.write(
                f"{hyper_type} "
                f"{condition_name} "
                f"run {run_number}/{NUM_RUNS} "
                f"seed={seed}\n"
            )

        if "error" in runs[-1]:

            print(
                f"  FAILED: "
                f"{runs[-1]['error']}"
            )

        else:

            print(
                f"  OK: "
                f"TT="
                f"{runs[-1]['average_travel_time']:.2f}s, "
                f"WT="
                f"{runs[-1]['average_waiting_time']:.2f}s, "
                f"Throughput="
                f"{runs[-1]['throughput']}"
            )

    successful_runs, stats = summarize_runs(runs)

    print(
        f"\n===== "
        f"{hyper_type.upper()} "
        f"{condition_name.upper()} COMPLETE ====="
    )

    print(
        f"Successful: "
        f"{len(successful_runs)}/{NUM_RUNS}"
    )

    if successful_runs:

        tt = stats["average_travel_time"]
        wt = stats["average_waiting_time"]
        tp = stats["throughput"]

        print(
            f"Average Travel Time: "
            f"{tt['mean']:.4f} s "
            f"(SD={tt['standard_deviation']:.4f})"
        )

        print(
            f"Average Waiting Time: "
            f"{wt['mean']:.4f} s "
            f"(SD={wt['standard_deviation']:.4f})"
        )

        print(
            f"Average Throughput: "
            f"{tp['mean']:.4f} "
            f"(SD={tp['standard_deviation']:.4f})"
        )

    print(f"JSON: {json_path}")
    print(f"TXT:  {txt_path}")

    return {
        "hyperparameter": hyper_type,
        "condition_name": condition_name,
        "hyperparameter_value": hyper_value,
        "num_runs_attempted": len(runs),
        "num_runs_successful": len(successful_runs),
        "statistics": stats,
        "runs": runs,
    }

# =============================
# MAIN RUNNER
# =============================

def main():
    args = parse_args()
    requested = args.hyper_type

    if not HYPER_FILE.exists():

        raise FileNotFoundError(
            f"Could not find hyperparameter "
            f"simulation file: {HYPER_FILE}"
        )

    print(
        "\n===== 3x3 QAOA "
        "HYPERPARAMETER RUNNER ====="
    )

    print(f"Requested experiment: {requested}")
    print(f"Runs per condition: {NUM_RUNS}")
    print(f"Alpha: {ALPHA_INDEX / 10:.1f}")
    print(f"Simulation file: {HYPER_FILE}")

    print(
        "Baseline: "
        f"gamma={BASE_GAMMA:.6f}, "
        f"beta={BASE_BETA:.6f}, "
        f"p={BASE_P}, "
        f"shots={BASE_SHOTS}"
    )

    print(
        "=====================================\n"
    )

    completed_results = {}

    # ---------------------------------
    # INDIVIDUAL HYPERPARAMETER SWEEPS
    # ---------------------------------

    if requested in HYPER_VALUES:

        values = HYPER_VALUES[requested]

        for condition_name, hyper_value in values.items():

            key = (
                f"{requested}_"
                f"{condition_name}"
            )

            completed_results[key] = (
                run_condition(
                    requested,
                    condition_name,
                    hyper_value
                )
            )


    # ---------------------------------
    # FULL 120-RUN EXPERIMENT
    # ---------------------------------

    elif requested == "all":

        for hyper_type in [
            "gamma",
            "beta",
            "p",
            "shots",
        ]:

            for (
                condition_name,
                hyper_value
            ) in HYPER_VALUES[
                hyper_type
            ].items():

                key = (
                    f"{hyper_type}_"
                    f"{condition_name}"
                )

                completed_results[key] = (
                    run_condition(
                        hyper_type,
                        condition_name,
                        hyper_value
                    )
                )


    print(
        "\n===== HYPERPARAMETER "
        "RUNNER COMPLETE ====="
    )

    print(
        f"Conditions completed: "
        f"{len(completed_results)}"
    )

    for key, result in completed_results.items():

        print(
            f"{key}: "
            f"{result['num_runs_successful']}"
            f"/{NUM_RUNS} successful"
        )

if __name__ == "__main__":
    main()