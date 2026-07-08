import csv
import json
import os
import re
import statistics
import subprocess
import sys
from pathlib import Path


# Run grid_2x2/2_classical.py five times and aggregate its 24 hourly result blocks.
NUM_RUNS = 3
RUN_TIMEOUT_SECONDS = 3600

BASE_DIR = Path(__file__).resolve().parent
SIMULATION_DIR = BASE_DIR / "grid_2x2"
SIMULATION_FILE = SIMULATION_DIR / "2_classical.py"
SUMO_CONFIG_FILE = BASE_DIR / "sim2x2_data.sumocfg"
OUTPUT_DIR = BASE_DIR / "seattle_classical_data"

JSON_OUTPUT_FILE = OUTPUT_DIR / "classical_simulation_results.json"
TXT_OUTPUT_FILE = OUTPUT_DIR / "classical_simulation_summary.txt"
CSV_OUTPUT_FILE = OUTPUT_DIR / "classical_hourly_summary.csv"
HEARTBEAT_FILE = OUTPUT_DIR / "heartbeat.txt"

METRIC_NAMES = (
    "departures",
    "throughput",
    "unfinished",
    "average_travel_time",
    "average_waiting_time",
)

# This matches PerformanceTracker.print_results() in
# grid_2x2/simulation_metrics.py. Travel/waiting time may legitimately be N/A.
HOURLY_RESULT_PATTERN = re.compile(
    r"^Results for\s+(?P<hour_label>.+?):\s*$"
    r"\s*^\s*Departures:\s*(?P<departures>\d+)\s*$"
    r"\s*^\s*Throughput:\s*(?P<throughput>\d+)\s*$"
    r"\s*^\s*Unfinished from this departure hour:\s*(?P<unfinished>\d+)\s*$"
    r"\s*^\s*Average Travel Time:\s*(?P<travel>N/A|[-+]?\d+(?:\.\d+)?)"
    r"(?:\s*s)?\s*$"
    r"\s*^\s*Average Waiting Time:\s*(?P<waiting>N/A|[-+]?\d+(?:\.\d+)?)"
    r"(?:\s*s)?\s*$",
    re.MULTILINE | re.IGNORECASE,
)


def parse_optional_float(value):
    return None if value.upper() == "N/A" else float(value)


def ensure_text(value):
    """Normalize subprocess output, including timeout output that may be bytes."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def build_subprocess_environment():
    """Make simulation_metrics.py importable by the classical simulation."""
    environment = os.environ.copy()
    python_paths = [str(SIMULATION_DIR)]
    existing_python_path = environment.get("PYTHONPATH")
    if existing_python_path:
        python_paths.append(existing_python_path)
    environment["PYTHONPATH"] = os.pathsep.join(python_paths)
    return environment


def extract_hourly_metrics(output):
    """Parse all 24 hourly metric blocks printed by the simulation."""
    hourly_metrics = []

    for hour_index, match in enumerate(HOURLY_RESULT_PATTERN.finditer(output)):
        hourly_metrics.append(
            {
                "hour": hour_index,
                "hour_label": match.group("hour_label").strip(),
                "departures": int(match.group("departures")),
                "throughput": int(match.group("throughput")),
                "unfinished": int(match.group("unfinished")),
                "average_travel_time": parse_optional_float(match.group("travel")),
                "average_waiting_time": parse_optional_float(match.group("waiting")),
            }
        )

    if len(hourly_metrics) != 24:
        raise ValueError(
            "Expected 24 hourly result blocks in the console output, "
            f"but found {len(hourly_metrics)}."
        )

    labels = [hour["hour_label"] for hour in hourly_metrics]
    if len(set(labels)) != 24:
        raise ValueError("The parsed hourly result labels are not unique.")

    return hourly_metrics


def calculate_stats(values):
    """Return descriptive statistics, excluding unavailable (None) values."""
    usable_values = [value for value in values if value is not None]
    count = len(usable_values)

    if count == 0:
        return {
            "count": 0,
            "mean": None,
            "median": None,
            "min": None,
            "max": None,
            "standard_deviation": None,
            "variance": None,
            "standard_error": None,
        }

    if count == 1:
        return {
            "count": 1,
            "mean": usable_values[0],
            "median": usable_values[0],
            "min": usable_values[0],
            "max": usable_values[0],
            "standard_deviation": 0.0,
            "variance": 0.0,
            "standard_error": 0.0,
        }

    standard_deviation = statistics.stdev(usable_values)
    return {
        "count": count,
        "mean": statistics.mean(usable_values),
        "median": statistics.median(usable_values),
        "min": min(usable_values),
        "max": max(usable_values),
        "standard_deviation": standard_deviation,
        "variance": statistics.variance(usable_values),
        "standard_error": standard_deviation / (count**0.5),
    }


def weighted_hourly_average(hourly_metrics, metric_name):
    """Combine hourly averages using each hour's completed-vehicle count."""
    weighted_values = [
        (hour[metric_name], hour["throughput"])
        for hour in hourly_metrics
        if hour[metric_name] is not None and hour["throughput"] > 0
    ]
    total_weight = sum(weight for _, weight in weighted_values)
    if total_weight == 0:
        return None
    return sum(value * weight for value, weight in weighted_values) / total_weight


def build_run_totals(hourly_metrics):
    return {
        "departures": sum(hour["departures"] for hour in hourly_metrics),
        "throughput": sum(hour["throughput"] for hour in hourly_metrics),
        "unfinished": sum(hour["unfinished"] for hour in hourly_metrics),
        "average_travel_time": weighted_hourly_average(
            hourly_metrics, "average_travel_time"
        ),
        "average_waiting_time": weighted_hourly_average(
            hourly_metrics, "average_waiting_time"
        ),
    }


def aggregate_hourly_results(successful_runs):
    hourly_summary = []

    for hour_index in range(24):
        hourly_rows = [run["hourly_metrics"][hour_index] for run in successful_runs]
        hourly_summary.append(
            {
                "hour": hour_index,
                "hour_label": hourly_rows[0]["hour_label"],
                "statistics": {
                    metric_name: calculate_stats(
                        [hour[metric_name] for hour in hourly_rows]
                    )
                    for metric_name in METRIC_NAMES
                },
            }
        )

    return hourly_summary


def aggregate_run_totals(successful_runs):
    return {
        metric_name: calculate_stats(
            [run["totals"][metric_name] for run in successful_runs]
        )
        for metric_name in METRIC_NAMES
    }


def format_number(value, decimals=2):
    return "N/A" if value is None else f"{value:.{decimals}f}"


def write_json(results):
    with JSON_OUTPUT_FILE.open("w", encoding="utf-8") as output_file:
        json.dump(results, output_file, indent=4)


def write_csv(hourly_summary):
    fieldnames = ["hour", "hour_label"]
    for metric_name in METRIC_NAMES:
        fieldnames.extend(
            [
                f"{metric_name}_mean",
                f"{metric_name}_standard_deviation",
                f"{metric_name}_min",
                f"{metric_name}_max",
                f"{metric_name}_count",
            ]
        )

    with CSV_OUTPUT_FILE.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()
        for hour in hourly_summary:
            row = {"hour": hour["hour"], "hour_label": hour["hour_label"]}
            for metric_name in METRIC_NAMES:
                stats = hour["statistics"][metric_name]
                row.update(
                    {
                        f"{metric_name}_mean": stats["mean"],
                        f"{metric_name}_standard_deviation": stats[
                            "standard_deviation"
                        ],
                        f"{metric_name}_min": stats["min"],
                        f"{metric_name}_max": stats["max"],
                        f"{metric_name}_count": stats["count"],
                    }
                )
            writer.writerow(row)


def write_text_summary(results):
    with TXT_OUTPUT_FILE.open("w", encoding="utf-8") as output_file:
        output_file.write("===== SEATTLE CLASSICAL SIMULATION SUMMARY =====\n\n")
        output_file.write(f"Source: {SIMULATION_FILE}\n")
        output_file.write(f"Runs attempted: {results['num_runs_attempted']}\n")
        output_file.write(f"Runs successful: {results['num_runs_successful']}\n")
        output_file.write(f"Runs failed: {results['num_runs_failed']}\n\n")

        output_file.write(
            "===== HOURLY MEAN +/- SAMPLE STANDARD DEVIATION =====\n\n"
        )
        for hour in results["hourly_summary"]:
            stats = hour["statistics"]
            output_file.write(f"{hour['hour']:02d} ({hour['hour_label']}):\n")
            output_file.write(
                "  Throughput: "
                f"{format_number(stats['throughput']['mean'])} +/- "
                f"{format_number(stats['throughput']['standard_deviation'])}\n"
            )
            output_file.write(
                "  Average travel time: "
                f"{format_number(stats['average_travel_time']['mean'])} +/- "
                f"{format_number(stats['average_travel_time']['standard_deviation'])} s\n"
            )
            output_file.write(
                "  Average waiting time: "
                f"{format_number(stats['average_waiting_time']['mean'])} +/- "
                f"{format_number(stats['average_waiting_time']['standard_deviation'])} s\n"
            )
            output_file.write(
                "  Departures: "
                f"{format_number(stats['departures']['mean'])} +/- "
                f"{format_number(stats['departures']['standard_deviation'])}\n"
            )
            output_file.write(
                "  Unfinished: "
                f"{format_number(stats['unfinished']['mean'])} +/- "
                f"{format_number(stats['unfinished']['standard_deviation'])}\n\n"
            )

        output_file.write("===== PER-RUN TOTAL STATISTICS =====\n\n")
        output_file.write(json.dumps(results["overall_statistics"], indent=4))
        output_file.write("\n")


def save_results(runs):
    successful_runs = [run for run in runs if "error" not in run]
    results = {
        "source_file": str(SIMULATION_FILE),
        "num_runs_planned": NUM_RUNS,
        "num_runs_attempted": len(runs),
        "num_runs_successful": len(successful_runs),
        "num_runs_failed": len(runs) - len(successful_runs),
        "runs": runs,
        "hourly_summary": (
            aggregate_hourly_results(successful_runs) if successful_runs else []
        ),
        "overall_statistics": (
            aggregate_run_totals(successful_runs) if successful_runs else {}
        ),
    }

    # Checkpoint after every run so an interrupted batch still leaves useful data.
    write_json(results)
    write_text_summary(results)
    write_csv(results["hourly_summary"])
    return results


def run_simulations():
    if not SIMULATION_FILE.is_file():
        raise FileNotFoundError(f"Simulation file not found: {SIMULATION_FILE}")
    if not SUMO_CONFIG_FILE.is_file():
        raise FileNotFoundError(f"SUMO configuration not found: {SUMO_CONFIG_FILE}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    runs = []

    print(f"Running {SIMULATION_FILE} {NUM_RUNS} times")
    print(f"Results will be saved in {OUTPUT_DIR}\n")

    for run_number in range(1, NUM_RUNS + 1):
        print(f"===== Classical run {run_number}/{NUM_RUNS} =====", flush=True)
        output = ""
        stderr = ""

        try:
            completed = subprocess.run(
                [sys.executable, str(SIMULATION_FILE)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                # 2_classical.py resolves sim2x2_data.sumocfg from this directory.
                cwd=BASE_DIR,
                env=build_subprocess_environment(),
                timeout=RUN_TIMEOUT_SECONDS,
                check=False,
            )
            output = completed.stdout
            stderr = completed.stderr

            if completed.returncode != 0:
                raise subprocess.CalledProcessError(
                    completed.returncode,
                    completed.args,
                    output=completed.stdout,
                    stderr=completed.stderr,
                )

            hourly_metrics = extract_hourly_metrics(output)
            totals = build_run_totals(hourly_metrics)
            runs.append(
                {
                    "run": run_number,
                    "hourly_metrics": hourly_metrics,
                    "totals": totals,
                    "raw_output": output,
                    "stderr": stderr,
                }
            )
            print(
                f"Parsed 24 hours | throughput={totals['throughput']} | "
                f"travel={format_number(totals['average_travel_time'])} s | "
                f"waiting={format_number(totals['average_waiting_time'])} s"
            )

        except subprocess.TimeoutExpired as error:
            runs.append(
                {
                    "run": run_number,
                    "error": f"Timeout after {RUN_TIMEOUT_SECONDS} seconds",
                    "raw_output": ensure_text(error.stdout) or output,
                    "stderr": ensure_text(error.stderr),
                }
            )
            print(f"Run timed out after {RUN_TIMEOUT_SECONDS} seconds.")

        except subprocess.CalledProcessError as error:
            runs.append(
                {
                    "run": run_number,
                    "error": "Simulation failed",
                    "return_code": error.returncode,
                    "raw_output": error.output or output,
                    "stderr": error.stderr or stderr,
                }
            )
            print(f"Run failed with return code {error.returncode}.")
            if error.stderr:
                print(error.stderr.strip())

        except ValueError as error:
            runs.append(
                {
                    "run": run_number,
                    "error": "Parsing failed",
                    "details": str(error),
                    "raw_output": output,
                    "stderr": stderr,
                }
            )
            print(f"Could not parse run output: {error}")

        HEARTBEAT_FILE.write_text(
            f"Completed run {run_number}/{NUM_RUNS}\n", encoding="utf-8"
        )
        save_results(runs)
        print()

    return save_results(runs)


def print_final_summary(results):
    print("===== FINAL HOURLY MEANS +/- STANDARD DEVIATIONS =====")
    for hour in results["hourly_summary"]:
        stats = hour["statistics"]
        print(
            f"{hour['hour']:02d} {hour['hour_label']}: "
            f"throughput {format_number(stats['throughput']['mean'])} +/- "
            f"{format_number(stats['throughput']['standard_deviation'])}, "
            f"travel {format_number(stats['average_travel_time']['mean'])} +/- "
            f"{format_number(stats['average_travel_time']['standard_deviation'])} s, "
            f"waiting {format_number(stats['average_waiting_time']['mean'])} +/- "
            f"{format_number(stats['average_waiting_time']['standard_deviation'])} s"
        )

    print(
        f"\nCompleted {results['num_runs_successful']}/"
        f"{results['num_runs_attempted']} runs successfully."
    )
    print("\n===== FILES SAVED =====")
    print(f"JSON: {JSON_OUTPUT_FILE}")
    print(f"TXT:  {TXT_OUTPUT_FILE}")
    print(f"CSV:  {CSV_OUTPUT_FILE}")


def main():
    results = run_simulations()
    print_final_summary(results)
    return 0 if results["num_runs_successful"] == NUM_RUNS else 1


if __name__ == "__main__":
    raise SystemExit(main())
