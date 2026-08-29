import argparse
import json
import math
import os
import re
import statistics
import subprocess
import sys
from pathlib import Path


# =============================
# CONFIG
# =============================

NUM_RUNS = 1
QAOA_SHOTS = 512
ALPHA_INDEX = 7

BASE_DIR = Path(__file__).parent
QUANTUM_DIR = BASE_DIR / "grid_3x3/3_quantum"
NOISE_FILE = QUANTUM_DIR / "a7_noise.py"
OUTPUT_DIR = BASE_DIR / "quantum_noise_data_3x3"
OUTPUT_DIR.mkdir(exist_ok=True)

# Frozen noise levels for the paper sensitivity analysis.
NOISE_LEVELS = {
    "depolarizing": {
        "low": 0.005,
        "medium": 0.01,
        "high": 0.02,
    },
    "readout": {
        "low": 0.01,
        "medium": 0.02,
        "high": 0.05,
    },
    "angle": {
        "low": 0.025,
        "medium": 0.05,
        "high": 0.10,
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
            "Run 3x3 QAOA synthetic-noise sensitivity experiments. "
            "Choose one noise mechanism. With no level flag, all three "
            "levels are run (30 runs). With --low/--medium/--high, only "
            "that level is run (10 runs)."
        )
    )

    parser.add_argument(
        "noise_type",
        choices=["depolarizing", "readout", "angle"],
        help="Noise mechanism to test."
    )

    level_group = parser.add_mutually_exclusive_group()
    level_group.add_argument("--low", action="store_true")
    level_group.add_argument("--medium", action="store_true")
    level_group.add_argument("--high", action="store_true")

    return parser.parse_args()


def selected_levels(args):
    if args.low:
        return ["low"]
    if args.medium:
        return ["medium"]
    if args.high:
        return ["high"]

    # No level flag = run the full 3-level experiment for this mechanism.
    return ["low", "medium", "high"]


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

def result_paths(noise_type, level_name):
    stem = f"{noise_type}_{level_name}"
    return (
        OUTPUT_DIR / f"{stem}_results.json",
        OUTPUT_DIR / f"{stem}_summary.txt",
    )


def write_level_results(noise_type, level_name, noise_level, runs):
    successful_runs, stats = summarize_runs(runs)
    json_path, txt_path = result_paths(noise_type, level_name)

    result_data = {
        "experiment": {
            "network": "3x3",
            "alpha_index": ALPHA_INDEX,
            "alpha": 0.7,
            "noise_type": noise_type,
            "level_name": level_name,
            "noise_level": noise_level,
            "num_runs_attempted": len(runs),
            "num_runs_target": NUM_RUNS,
            "num_runs_successful": len(successful_runs),
            "qaoa_shots": QAOA_SHOTS,
            "seeds": SEEDS,
            "source_file": str(NOISE_FILE),
        },
        "runs": runs,
        "statistics": stats,
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result_data, f, indent=4)

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("===== 3x3 QAOA NOISE SENSITIVITY SUMMARY =====\n\n")
        f.write(f"Noise type: {noise_type}\n")
        f.write(f"Level: {level_name}\n")
        f.write(f"Noise value: {noise_level}\n")
        f.write(f"Runs attempted: {len(runs)}/{NUM_RUNS}\n")
        f.write(f"Runs successful: {len(successful_runs)}/{NUM_RUNS}\n\n")

        for metric_name, metric_stats in stats.items():
            f.write(f"{metric_name}:\n")
            f.write(json.dumps(metric_stats, indent=4))
            f.write("\n\n")

    return json_path, txt_path, successful_runs, stats


def write_combined_results(noise_type, level_results):
    json_path = OUTPUT_DIR / f"{noise_type}_all_levels_results.json"
    txt_path = OUTPUT_DIR / f"{noise_type}_all_levels_summary.txt"

    combined = {
        "experiment": {
            "network": "3x3",
            "alpha_index": ALPHA_INDEX,
            "alpha": 0.7,
            "noise_type": noise_type,
            "levels": {
                name: NOISE_LEVELS[noise_type][name]
                for name in level_results
            },
            "runs_per_level": NUM_RUNS,
            "total_target_runs": NUM_RUNS * len(level_results),
            "qaoa_shots": QAOA_SHOTS,
        },
        "levels": level_results,
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(combined, f, indent=4)

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("===== 3x3 QAOA NOISE SENSITIVITY — ALL LEVELS =====\n\n")
        f.write(f"Noise type: {noise_type}\n")
        f.write(f"Runs per level: {NUM_RUNS}\n\n")

        for level_name in level_results:
            info = level_results[level_name]
            stats = info["statistics"]

            f.write(
                f"--- {level_name.upper()} "
                f"(noise={info['noise_level']}) ---\n"
            )
            f.write(
                f"Successful runs: "
                f"{info['num_runs_successful']}/{NUM_RUNS}\n"
            )

            tt = stats.get("average_travel_time", {})
            wt = stats.get("average_waiting_time", {})
            tp = stats.get("throughput", {})

            f.write(
                f"Travel Time mean: {tt.get('mean', 0):.4f} s "
                f"(95% CI {tt.get('ci95_low', 0):.4f}, "
                f"{tt.get('ci95_high', 0):.4f})\n"
            )
            f.write(
                f"Waiting Time mean: {wt.get('mean', 0):.4f} s "
                f"(95% CI {wt.get('ci95_low', 0):.4f}, "
                f"{wt.get('ci95_high', 0):.4f})\n"
            )
            f.write(
                f"Throughput mean: {tp.get('mean', 0):.4f} "
                f"(95% CI {tp.get('ci95_low', 0):.4f}, "
                f"{tp.get('ci95_high', 0):.4f})\n\n"
            )

    return json_path, txt_path


# =============================
# MAIN RUNNER
# =============================

def main():
    args = parse_args()
    noise_type = args.noise_type
    levels = selected_levels(args)

    if not NOISE_FILE.exists():
        raise FileNotFoundError(
            f"Could not find noise simulation file: {NOISE_FILE}"
        )

    total_runs = NUM_RUNS * len(levels)

    print("\n===== 3x3 QAOA NOISE RUNNER =====")
    print(f"Noise type: {noise_type}")
    print(f"Levels: {levels}")
    print(f"Runs per level: {NUM_RUNS}")
    print(f"Total runs: {total_runs}")
    print(f"QAOA shots: {QAOA_SHOTS}")
    print(f"Simulation file: {NOISE_FILE}")
    print("=================================\n")

    combined_level_results = {}

    for level_name in levels:
        noise_level = NOISE_LEVELS[noise_type][level_name]

        print(
            f"\n===== {noise_type.upper()} — "
            f"{level_name.upper()} ({noise_level}) ====="
        )

        runs = []

        for run_number in range(1, NUM_RUNS + 1):
            seed = SEEDS[run_number - 1]

            print(
                f"{noise_type}/{level_name}: "
                f"Run {run_number}/{NUM_RUNS} "
                f"(seed={seed})"
            )

            output = ""

            try:
                run_env = os.environ.copy()
                run_env["QAOA_SHOTS"] = str(QAOA_SHOTS)

                command = [
                    sys.executable,
                    str(NOISE_FILE),
                    str(ALPHA_INDEX),
                    noise_type,
                    str(noise_level),
                    str(seed),
                ]

                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    cwd=BASE_DIR,
                    timeout=7200,
                    env=run_env,
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
                    "noise_type": noise_type,
                    "level_name": level_name,
                    "noise_level": noise_level,
                    "throughput": metrics["throughput"],
                    "average_waiting_time": metrics["average_waiting_time"],
                    "average_travel_time": metrics["average_travel_time"],
                    "vehicles_inserted": metrics["vehicles_inserted"],
                    "vehicles_remaining": metrics["vehicles_remaining"],
                    "shots": metrics["shots"],
                    "num_decisions": metrics["num_decisions"],
                    "optimal_hits": metrics["optimal_hits"],
                    "optimum_recovery_rate": metrics["optimum_recovery_rate"],
                    "average_selected_energy": metrics["average_selected_energy"],
                    "average_exact_min_energy": metrics["average_exact_min_energy"],
                    "average_optimality_gap": metrics["average_optimality_gap"],
                    "maximum_optimality_gap": metrics["maximum_optimality_gap"],
                    "average_energy_reduction": metrics["average_energy_reduction"],
                    "raw_output": output,
                })

            except subprocess.TimeoutExpired:
                runs.append({
                    "run": run_number,
                    "seed": seed,
                    "noise_type": noise_type,
                    "level_name": level_name,
                    "noise_level": noise_level,
                    "error": "Timeout (>2 hours)",
                })

            except subprocess.CalledProcessError as e:
                runs.append({
                    "run": run_number,
                    "seed": seed,
                    "noise_type": noise_type,
                    "level_name": level_name,
                    "noise_level": noise_level,
                    "error": "Simulation failed",
                    "details": str(e),
                    "stderr": e.stderr,
                    "raw_output": e.output,
                })

            except ValueError as e:
                runs.append({
                    "run": run_number,
                    "seed": seed,
                    "noise_type": noise_type,
                    "level_name": level_name,
                    "noise_level": noise_level,
                    "error": "Parsing failed",
                    "details": str(e),
                    "raw_output": output,
                })

            # Save after every run so progress is not lost if a batch stops.
            json_path, txt_path, successful_runs, stats = write_level_results(
                noise_type,
                level_name,
                noise_level,
                runs,
            )

            heartbeat_path = OUTPUT_DIR / "noise_heartbeat.txt"
            with open(heartbeat_path, "w", encoding="utf-8") as f:
                f.write(
                    f"{noise_type} {level_name} "
                    f"run {run_number}/{NUM_RUNS} "
                    f"seed={seed}\n"
                )

            if "error" in runs[-1]:
                print(f"  FAILED: {runs[-1]['error']}")
            else:
                print(
                    f"  OK: TT={runs[-1]['average_travel_time']:.2f}s, "
                    f"WT={runs[-1]['average_waiting_time']:.2f}s, "
                    f"Throughput={runs[-1]['throughput']}"
                )

        successful_runs, stats = summarize_runs(runs)

        combined_level_results[level_name] = {
            "noise_level": noise_level,
            "num_runs_attempted": len(runs),
            "num_runs_successful": len(successful_runs),
            "statistics": stats,
            "runs": runs,
        }

        print(f"\n===== {level_name.upper()} COMPLETE =====")
        print(
            f"Successful: {len(successful_runs)}/{NUM_RUNS}"
        )

        if successful_runs:
            tt = stats["average_travel_time"]
            wt = stats["average_waiting_time"]
            tp = stats["throughput"]

            print(
                f"Average Travel Time: {tt['mean']:.4f} s "
                f"(SD={tt['standard_deviation']:.4f})"
            )
            print(
                f"Average Waiting Time: {wt['mean']:.4f} s "
                f"(SD={wt['standard_deviation']:.4f})"
            )
            print(
                f"Average Throughput: {tp['mean']:.4f} "
                f"(SD={tp['standard_deviation']:.4f})"
            )

        print(f"JSON: {json_path}")
        print(f"TXT:  {txt_path}")

    # If all three levels were requested, also save one combined mechanism file.
    if len(levels) == 3:
        combined_json, combined_txt = write_combined_results(
            noise_type,
            combined_level_results,
        )

        print("\n===== FULL NOISE EXPERIMENT COMPLETE =====")
        print(f"Noise type: {noise_type}")
        print(f"Total target runs: {total_runs}")
        print(f"Combined JSON: {combined_json}")
        print(f"Combined TXT:  {combined_txt}")


if __name__ == "__main__":
    main()
