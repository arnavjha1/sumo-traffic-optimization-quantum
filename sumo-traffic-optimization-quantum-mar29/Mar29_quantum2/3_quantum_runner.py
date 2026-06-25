import subprocess
import re
import statistics
import json
from pathlib import Path


# =============================
# CONFIG
# =============================

NUM_RUNS = 10

BASE_DIR = Path(__file__).parent
QUANTUM_DIR = BASE_DIR / "grid_2x2/3_quantum"
OUTPUT_DIR = BASE_DIR / "quantum_data"

OUTPUT_DIR.mkdir(exist_ok=True)

FILES = [QUANTUM_DIR / f"3_quantum_a{i}.py" for i in range(11)]


# =============================
# PARSING
# =============================

def extract_metrics(output):
    travel_match = re.search(
        r"Average Travel Time:.*?Overall:\s+([\d.]+)",
        output,
        re.DOTALL
    )

    waiting_match = re.search(
        r"Average Waiting Time:.*?Overall:\s+([\d.]+)",
        output,
        re.DOTALL
    )

    throughput_match = re.search(
        r"Throughput:.*?Overall:\s+(\d+)",
        output,
        re.DOTALL
    )

    if not travel_match or not waiting_match or not throughput_match:
        raise ValueError("Could not parse travel time, waiting time, or throughput.")

    return {
        "throughput": int(throughput_match.group(1)),
        "average_waiting_time": float(waiting_match.group(1)),
        "average_travel_time": float(travel_match.group(1)),
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
        }

    stdev = statistics.stdev(values)

    return {
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "min": min(values),
        "max": max(values),
        "standard_deviation": stdev,
        "variance": statistics.variance(values),
        "standard_error": stdev / (len(values) ** 0.5),
    }


# =============================
# MAIN RUNNER
# =============================

all_results = {}

throughput_averages = []
waiting_time_averages = []
travel_time_averages = []

for file_path in FILES:
    simulation_name = file_path.stem

    if not file_path.exists():
        print(f"Skipping missing file: {file_path}")
        continue

    print(f"\n===== Running {simulation_name} =====")

    runs = []

    for run_number in range(1, NUM_RUNS + 1):
        print(f"{simulation_name}: Run {run_number}/{NUM_RUNS}")

        try:

            result = subprocess.run(
                ["python", str(file_path)],
                capture_output=True,
                text=True,
                cwd=BASE_DIR,
                timeout=3600
            )

            output = result.stdout

            if result.returncode != 0:
                raise subprocess.CalledProcessError(
                    result.returncode,
                    result.args,
                    output=result.stdout,
                    stderr=result.stderr
                )

            metrics = extract_metrics(output)

            runs.append({
                "run": run_number,
                "throughput": metrics["throughput"],
                "average_waiting_time": metrics["average_waiting_time"],
                "average_travel_time": metrics["average_travel_time"],
                "raw_output": output
            })

        except subprocess.TimeoutExpired:
            runs.append({
                "run": run_number,
                "error": "Timeout (>1 hour)"
            })

        except subprocess.CalledProcessError as e:
            runs.append({
                "run": run_number,
                "error": "Simulation failed",
                "details": str(e),
                "stderr": e.stderr,
                "raw_output": e.output
            })

        except ValueError as e:
            runs.append({
                "run": run_number,
                "error": "Parsing failed",
                "details": str(e),
                "raw_output": output
            })

        with open("heartbeat.txt", "w") as f:
            f.write(
                f"{simulation_name} "
                f"run {run_number}/{NUM_RUNS}"
            )

    successful_runs = [run for run in runs if "error" not in run]

    throughputs = [run["throughput"] for run in successful_runs]
    waiting_times = [run["average_waiting_time"] for run in successful_runs]
    travel_times = [run["average_travel_time"] for run in successful_runs]

    throughput_stats = calculate_stats(throughputs)
    waiting_stats = calculate_stats(waiting_times)
    travel_stats = calculate_stats(travel_times)

    if successful_runs:
        throughput_averages.append(throughput_stats["mean"])
        waiting_time_averages.append(waiting_stats["mean"])
        travel_time_averages.append(travel_stats["mean"])

    all_results[simulation_name] = {
        "source_file": str(file_path),
        "num_runs_attempted": NUM_RUNS,
        "num_runs_successful": len(successful_runs),
        "runs": runs,
        "statistics": {
            "throughput": throughput_stats,
            "average_waiting_time": waiting_stats,
            "average_travel_time": travel_stats,
        }
    }


# =============================
# OVERALL SUMMARY
# =============================

overall_summary = {
    "throughput": calculate_stats(throughput_averages),
    "average_waiting_time": calculate_stats(waiting_time_averages),
    "average_travel_time": calculate_stats(travel_time_averages),
}

all_results["summary"] = {
    "throughput_averages_by_file": throughput_averages,
    "waiting_time_averages_by_file": waiting_time_averages,
    "travel_time_averages_by_file": travel_time_averages,
    "overall_summary": overall_summary,
}


# =============================
# WRITE FILES
# =============================

json_output_file = OUTPUT_DIR / "quantum_simulation_results.json"
txt_output_file = OUTPUT_DIR / "quantum_simulation_summary.txt"

with open(json_output_file, "w", encoding="utf-8") as f:
    json.dump(all_results, f, indent=4)

with open(txt_output_file, "w", encoding="utf-8") as f:
    f.write("===== QUANTUM SIMULATION SUMMARY =====\n\n")

    f.write("Throughput averages by file:\n")
    f.write(str(throughput_averages) + "\n\n")

    f.write("Waiting time averages by file:\n")
    f.write(str(waiting_time_averages) + "\n\n")

    f.write("Travel time averages by file:\n")
    f.write(str(travel_time_averages) + "\n\n")

    f.write("===== OVERALL AVERAGES =====\n\n")
    f.write(f"Overall Throughput Average: {overall_summary['throughput'].get('mean', 0):.2f}\n")
    f.write(f"Overall Waiting Time Average: {overall_summary['average_waiting_time'].get('mean', 0):.2f} s\n")
    f.write(f"Overall Travel Time Average: {overall_summary['average_travel_time'].get('mean', 0):.2f} s\n\n")

    f.write("===== FULL OVERALL STATS =====\n\n")
    f.write(json.dumps(overall_summary, indent=4))


# =============================
# PRINT RESULTS
# =============================

print("\n===== FILE AVERAGES =====")

print("\nThroughput averages by file:")
print(throughput_averages)

print("\nWaiting time averages by file:")
print(waiting_time_averages)

print("\nTravel time averages by file:")
print(travel_time_averages)

print("\n===== OVERALL AVERAGES =====")
print(f"Overall Throughput Average: {overall_summary['throughput'].get('mean', 0):.2f}")
print(f"Overall Waiting Time Average: {overall_summary['average_waiting_time'].get('mean', 0):.2f} s")
print(f"Overall Travel Time Average: {overall_summary['average_travel_time'].get('mean', 0):.2f} s")

print("\n===== FILES SAVED =====")
print(f"JSON: {json_output_file}")
print(f"TXT:  {txt_output_file}")