import csv
import json
import os
import re
import statistics
import subprocess
import sys
from pathlib import Path


# ============================================================
# 3x3 SEATTLE QAOA BATCH RUNNER
# ============================================================

NUM_RUNS = 10
RUN_TIMEOUT_SECONDS = 21600  # 6 hours per full 24-hour simulation

BASE_DIR = Path(__file__).resolve().parent
SIMULATION_DIR = BASE_DIR / "grid_3x3"
SIMULATION_FILE = SIMULATION_DIR / "4_quantum.py"
ANNEALER_FILE = SIMULATION_DIR / "annealer_quantum.py"
SUMO_CONFIG_FILE = SIMULATION_DIR / "sim3x3_data.sumocfg"

OUTPUT_DIR = BASE_DIR / "seattle_3x3_quantum_data_C"

JSON_OUTPUT_FILE = OUTPUT_DIR / "quantum_3x3_seattle_results.json"
TXT_OUTPUT_FILE = OUTPUT_DIR / "quantum_3x3_seattle_summary.txt"
CSV_OUTPUT_FILE = OUTPUT_DIR / "quantum_3x3_seattle_hourly_summary.csv"
PARAMS_CSV_FILE = OUTPUT_DIR / "quantum_3x3_seattle_hourly_qaoa_params.csv"
ENERGY_CSV_FILE = OUTPUT_DIR / "quantum_3x3_seattle_hourly_energy_summary.csv"
HEARTBEAT_FILE = OUTPUT_DIR / "heartbeat.txt"


# ============================================================
# OUTPUT PARSERS
# ============================================================

HOURLY_TRAFFIC_PATTERN = re.compile(
    r"^Hour\s+(?P<hour>\d{2}):\s*"
    r"TT=(?P<travel>N/A|[-+]?\d+(?:\.\d+)?)"
    r"(?:\s*s)?,\s*"
    r"WT=(?P<waiting>N/A|[-+]?\d+(?:\.\d+)?)"
    r"(?:\s*s)?,\s*"
    r"n=(?P<count>\d+)"
    r"(?:,\s*window=.*)?$",
    re.MULTILINE | re.IGNORECASE,
)

OVERALL_TRAFFIC_PATTERN = re.compile(
    r"Post-warm-up Overall:\s*"
    r"\s*Average Travel Time:\s*(?P<travel>[-+]?\d+(?:\.\d+)?)\s*s"
    r"\s*Average Waiting Time:\s*(?P<waiting>[-+]?\d+(?:\.\d+)?)\s*s"
    r"\s*Measured completed vehicles:\s*(?P<count>\d+)",
    re.MULTILINE | re.IGNORECASE,
)

JSON_PATTERNS = {
    "hourly_qaoa_parameters": re.compile(
        r"^HOURLY_QAOA_PARAMS_JSON:\s*(\{.*\})\s*$",
        re.MULTILINE,
    ),
    "hourly_energy": re.compile(
        r"^HOURLY_ENERGY_JSON:\s*(\{.*\})\s*$",
        re.MULTILINE,
    ),
    "overall_energy": re.compile(
        r"^ENERGY_JSON:\s*(\{.*\})\s*$",
        re.MULTILINE,
    ),
}


def parse_optional_float(value):
    return None if value.upper() == "N/A" else float(value)


def ensure_text(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def build_subprocess_environment():
    env = os.environ.copy()
    python_paths = [str(SIMULATION_DIR)]
    existing = env.get("PYTHONPATH")
    if existing:
        python_paths.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(python_paths)
    return env


def extract_last_json(output, key, required=False):
    matches = JSON_PATTERNS[key].findall(output)

    if not matches:
        if required:
            raise ValueError(f"Missing required {key} JSON block.")
        return None

    for raw in reversed(matches):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    if required:
        raise ValueError(f"Could not decode required {key} JSON block.")
    return None


def normalize_hourly_json(raw):
    if not raw:
        return {}

    normalized = {}
    for key, value in raw.items():
        try:
            hour = int(key)
        except (TypeError, ValueError):
            continue

        if 0 <= hour <= 23:
            normalized[hour] = value

    return normalized


def extract_hourly_traffic(output):
    hourly = {}

    for match in HOURLY_TRAFFIC_PATTERN.finditer(output):
        hour = int(match.group("hour"))
        if 0 <= hour <= 23:
            hourly[hour] = {
                "hour": hour,
                "average_travel_time": parse_optional_float(match.group("travel")),
                "average_waiting_time": parse_optional_float(match.group("waiting")),
                "completed_vehicles": int(match.group("count")),
            }

    if len(hourly) != 24:
        missing = sorted(set(range(24)) - set(hourly))
        raise ValueError(
            f"Expected 24 hourly traffic rows, found {len(hourly)}. "
            f"Missing: {missing}"
        )

    return [hourly[h] for h in range(24)]


def extract_overall_traffic(output):
    match = OVERALL_TRAFFIC_PATTERN.search(output)
    if not match:
        raise ValueError("Could not parse Post-warm-up Overall traffic metrics.")

    return {
        "average_travel_time": float(match.group("travel")),
        "average_waiting_time": float(match.group("waiting")),
        "completed_vehicles": int(match.group("count")),
    }


def extract_run_data(output):
    hourly_traffic = extract_hourly_traffic(output)
    overall_traffic = extract_overall_traffic(output)

    hourly_params = normalize_hourly_json(
        extract_last_json(output, "hourly_qaoa_parameters", required=True)
    )
    if len(hourly_params) != 24:
        missing = sorted(set(range(24)) - set(hourly_params))
        raise ValueError(
            f"Expected 24 hourly QAOA parameter sets, found {len(hourly_params)}. "
            f"Missing: {missing}"
        )

    hourly_energy = normalize_hourly_json(
        extract_last_json(output, "hourly_energy", required=True)
    )
    if len(hourly_energy) != 24:
        missing = sorted(set(range(24)) - set(hourly_energy))
        raise ValueError(
            f"Expected 24 hourly energy entries, found {len(hourly_energy)}. "
            f"Missing: {missing}"
        )

    overall_energy = extract_last_json(
        output, "overall_energy", required=True
    )

    return {
        "hourly_traffic": hourly_traffic,
        "overall_traffic": overall_traffic,
        "hourly_qaoa_parameters": hourly_params,
        "hourly_energy": hourly_energy,
        "overall_energy": overall_energy,
    }


# ============================================================
# STATISTICS
# ============================================================

def calculate_stats(values):
    usable = [v for v in values if v is not None]
    n = len(usable)

    if n == 0:
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

    if n == 1:
        return {
            "count": 1,
            "mean": usable[0],
            "median": usable[0],
            "min": usable[0],
            "max": usable[0],
            "standard_deviation": 0.0,
            "variance": 0.0,
            "standard_error": 0.0,
        }

    sd = statistics.stdev(usable)
    return {
        "count": n,
        "mean": statistics.mean(usable),
        "median": statistics.median(usable),
        "min": min(usable),
        "max": max(usable),
        "standard_deviation": sd,
        "variance": statistics.variance(usable),
        "standard_error": sd / (n ** 0.5),
    }


def aggregate_hourly_traffic(successful_runs):
    result = []

    for hour in range(24):
        rows = [run["hourly_traffic"][hour] for run in successful_runs]

        result.append({
            "hour": hour,
            "statistics": {
                "average_travel_time": calculate_stats(
                    [r["average_travel_time"] for r in rows]
                ),
                "average_waiting_time": calculate_stats(
                    [r["average_waiting_time"] for r in rows]
                ),
                "completed_vehicles": calculate_stats(
                    [r["completed_vehicles"] for r in rows]
                ),
            },
        })

    return result


def aggregate_overall_traffic(successful_runs):
    return {
        field: calculate_stats(
            [run["overall_traffic"][field] for run in successful_runs]
        )
        for field in (
            "average_travel_time",
            "average_waiting_time",
            "completed_vehicles",
        )
    }


def aggregate_hourly_energy(successful_runs):
    fields = (
        "num_decisions",
        "optimal_hits",
        "optimum_recovery_rate",
        "average_selected_energy",
        "average_exact_min_energy",
        "average_optimality_gap",
        "maximum_optimality_gap",
        "average_energy_reduction",
    )

    summary = []

    for hour in range(24):
        rows = [
            run["hourly_energy"].get(hour, {})
            for run in successful_runs
        ]

        summary.append({
            "hour": hour,
            "statistics": {
                field: calculate_stats([row.get(field) for row in rows])
                for field in fields
            },
        })

    return summary


def aggregate_overall_energy(successful_runs):
    fields = (
        "shots",
        "num_decisions",
        "optimal_hits",
        "optimum_recovery_rate",
        "average_selected_energy",
        "average_exact_min_energy",
        "average_optimality_gap",
        "maximum_optimality_gap",
        "average_energy_reduction",
    )

    return {
        field: calculate_stats(
            [run["overall_energy"].get(field) for run in successful_runs]
        )
        for field in fields
    }


def format_number(value, decimals=2):
    return "N/A" if value is None else f"{value:.{decimals}f}"


# ============================================================
# FILE WRITERS
# ============================================================

def write_json(results):
    with JSON_OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=4)


def write_hourly_csv(hourly_summary):
    fieldnames = ["hour"]

    for metric in (
        "average_travel_time",
        "average_waiting_time",
        "completed_vehicles",
    ):
        for stat in (
            "mean",
            "standard_deviation",
            "median",
            "min",
            "max",
            "count",
        ):
            fieldnames.append(f"{metric}_{stat}")

    with CSV_OUTPUT_FILE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for hour in hourly_summary:
            row = {"hour": hour["hour"]}

            for metric, stats in hour["statistics"].items():
                for stat in (
                    "mean",
                    "standard_deviation",
                    "median",
                    "min",
                    "max",
                    "count",
                ):
                    row[f"{metric}_{stat}"] = stats[stat]

            writer.writerow(row)


def write_params_csv(successful_runs):
    fieldnames = [
        "run",
        "hour",
        "gamma",
        "beta",
        "p",
        "wins",
        "calibration_decisions",
    ]

    with PARAMS_CSV_FILE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for run in successful_runs:
            for hour in range(24):
                params = run["hourly_qaoa_parameters"].get(hour, {})
                writer.writerow({
                    "run": run["run"],
                    "hour": hour,
                    "gamma": params.get("gamma"),
                    "beta": params.get("beta"),
                    "p": params.get("p"),
                    "wins": params.get("wins"),
                    "calibration_decisions": params.get(
                        "calibration_decisions"
                    ),
                })


def write_energy_csv(hourly_summary):
    fields = (
        "num_decisions",
        "optimal_hits",
        "optimum_recovery_rate",
        "average_selected_energy",
        "average_exact_min_energy",
        "average_optimality_gap",
        "maximum_optimality_gap",
        "average_energy_reduction",
    )

    fieldnames = ["hour"]

    for field in fields:
        for stat in (
            "mean",
            "standard_deviation",
            "median",
            "min",
            "max",
            "count",
        ):
            fieldnames.append(f"{field}_{stat}")

    with ENERGY_CSV_FILE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for hour in hourly_summary:
            row = {"hour": hour["hour"]}

            for field, stats in hour["statistics"].items():
                for stat in (
                    "mean",
                    "standard_deviation",
                    "median",
                    "min",
                    "max",
                    "count",
                ):
                    row[f"{field}_{stat}"] = stats[stat]

            writer.writerow(row)


def write_text_summary(results):
    with TXT_OUTPUT_FILE.open("w", encoding="utf-8") as f:
        f.write("===== 3x3 SEATTLE QAOA SUMMARY =====\n\n")
        f.write(f"Source: {SIMULATION_FILE}\n")
        f.write(f"Runs planned: {results['num_runs_planned']}\n")
        f.write(f"Runs attempted: {results['num_runs_attempted']}\n")
        f.write(f"Runs successful: {results['num_runs_successful']}\n")
        f.write(f"Runs failed: {results['num_runs_failed']}\n\n")

        f.write("===== HOURLY TRAFFIC MEAN +/- SAMPLE SD =====\n\n")

        for hour in results["hourly_traffic_summary"]:
            s = hour["statistics"]

            f.write(
                f"Hour {hour['hour']:02d}: "
                f"TT={format_number(s['average_travel_time']['mean'])} +/- "
                f"{format_number(s['average_travel_time']['standard_deviation'])} s, "
                f"WT={format_number(s['average_waiting_time']['mean'])} +/- "
                f"{format_number(s['average_waiting_time']['standard_deviation'])} s, "
                f"n={format_number(s['completed_vehicles']['mean'])} +/- "
                f"{format_number(s['completed_vehicles']['standard_deviation'])}\n"
            )

        f.write("\n===== OVERALL TRAFFIC STATISTICS =====\n\n")
        f.write(json.dumps(results["overall_traffic_statistics"], indent=4))

        f.write("\n\n===== OVERALL ENERGY STATISTICS =====\n\n")
        f.write(json.dumps(results["overall_energy_statistics"], indent=4))
        f.write("\n")


def save_results(runs):
    successful_runs = [r for r in runs if "error" not in r]

    results = {
        "source_file": str(SIMULATION_FILE),
        "num_runs_planned": NUM_RUNS,
        "num_runs_attempted": len(runs),
        "num_runs_successful": len(successful_runs),
        "num_runs_failed": len(runs) - len(successful_runs),
        "runs": runs,
        "hourly_traffic_summary": (
            aggregate_hourly_traffic(successful_runs)
            if successful_runs else []
        ),
        "overall_traffic_statistics": (
            aggregate_overall_traffic(successful_runs)
            if successful_runs else {}
        ),
        "hourly_energy_summary": (
            aggregate_hourly_energy(successful_runs)
            if successful_runs else []
        ),
        "overall_energy_statistics": (
            aggregate_overall_energy(successful_runs)
            if successful_runs else {}
        ),
    }

    write_json(results)
    write_text_summary(results)
    write_hourly_csv(results["hourly_traffic_summary"])
    write_params_csv(successful_runs)
    write_energy_csv(results["hourly_energy_summary"])

    return results


# ============================================================
# RUN LOOP
# ============================================================

def run_simulations():
    if not SIMULATION_FILE.is_file():
        raise FileNotFoundError(
            f"Simulation file not found: {SIMULATION_FILE}"
        )

    if not ANNEALER_FILE.is_file():
        raise FileNotFoundError(
            f"Annealer not found: {ANNEALER_FILE}"
        )

    if not SUMO_CONFIG_FILE.is_file():
        raise FileNotFoundError(
            f"SUMO config not found: {SUMO_CONFIG_FILE}"
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    runs = []

    print(f"Running {SIMULATION_FILE} {NUM_RUNS} times")
    print(f"Results will be saved in {OUTPUT_DIR}\n")

    for run_number in range(1, NUM_RUNS + 1):
        print(
            f"===== 3x3 Seattle QAOA run "
            f"{run_number}/{NUM_RUNS} =====",
            flush=True,
        )

        output = ""
        stderr = ""

        try:
            completed = subprocess.run(
                [sys.executable, str(SIMULATION_FILE)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=BASE_DIR,
                env=build_subprocess_environment(),
                timeout=RUN_TIMEOUT_SECONDS,
                check=False,
            )

            output = completed.stdout
            stderr = completed.stderr or ""

            if completed.returncode != 0:
                raise subprocess.CalledProcessError(
                    completed.returncode,
                    completed.args,
                    output=completed.stdout,
                    stderr=completed.stderr,
                )

            parsed = extract_run_data(output)

            run_record = {
                "run": run_number,
                **parsed,
                "raw_output": output,
                "stderr": stderr,
            }

            runs.append(run_record)

            overall = parsed["overall_traffic"]

            print(
                f"Parsed 24 hours | "
                f"completed={overall['completed_vehicles']} | "
                f"TT={format_number(overall['average_travel_time'])} s | "
                f"WT={format_number(overall['average_waiting_time'])} s"
            )

        except subprocess.TimeoutExpired as error:
            runs.append({
                "run": run_number,
                "error": f"Timeout after {RUN_TIMEOUT_SECONDS} seconds",
                "raw_output": ensure_text(error.stdout) or output,
                "stderr": ensure_text(error.stderr),
            })
            print(
                f"Run timed out after "
                f"{RUN_TIMEOUT_SECONDS} seconds."
            )

        except subprocess.CalledProcessError as error:
            runs.append({
                "run": run_number,
                "error": "Simulation failed",
                "return_code": error.returncode,
                "raw_output": error.output or output,
                "stderr": error.stderr or stderr,
            })
            print(
                f"Run failed with return code "
                f"{error.returncode}."
            )

            if error.stderr:
                print(str(error.stderr).strip())

        except ValueError as error:
            runs.append({
                "run": run_number,
                "error": "Parsing failed",
                "details": str(error),
                "raw_output": output,
                "stderr": stderr,
            })
            print(f"Could not parse run output: {error}")

        HEARTBEAT_FILE.write_text(
            f"Completed run {run_number}/{NUM_RUNS}\n",
            encoding="utf-8",
        )

        # Checkpoint after EVERY run.
        save_results(runs)
        print()

    return save_results(runs)


def print_final_summary(results):
    print(
        "===== FINAL 3x3 SEATTLE QAOA "
        "HOURLY MEANS +/- SD ====="
    )

    for hour in results["hourly_traffic_summary"]:
        s = hour["statistics"]

        print(
            f"Hour {hour['hour']:02d}: "
            f"TT {format_number(s['average_travel_time']['mean'])} +/- "
            f"{format_number(s['average_travel_time']['standard_deviation'])} s | "
            f"WT {format_number(s['average_waiting_time']['mean'])} +/- "
            f"{format_number(s['average_waiting_time']['standard_deviation'])} s | "
            f"n {format_number(s['completed_vehicles']['mean'])} +/- "
            f"{format_number(s['completed_vehicles']['standard_deviation'])}"
        )

    print(
        f"\nCompleted {results['num_runs_successful']}/"
        f"{results['num_runs_attempted']} runs successfully."
    )

    print("\n===== FILES SAVED =====")
    print(f"JSON:        {JSON_OUTPUT_FILE}")
    print(f"TXT:         {TXT_OUTPUT_FILE}")
    print(f"Traffic CSV: {CSV_OUTPUT_FILE}")
    print(f"Params CSV:  {PARAMS_CSV_FILE}")
    print(f"Energy CSV:  {ENERGY_CSV_FILE}")


def main():
    results = run_simulations()
    print_final_summary(results)

    return (
        0
        if results["num_runs_successful"] == NUM_RUNS
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
