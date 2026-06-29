# SEATTLE CASE STUDY - TRAVEL TIME DATA
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


hours = list(range(24))

#             12-1    1-2    2-3    3-4    4-5    5-6    6-7    7-8    8-9   9-10  10-11  11-12   12-1    1-2    2-3    3-4    4-5    5-6    6-7    7-8    8-9   9-10  10-11  11-12
fixed     = [57.33, 59.84, 59.27, 59.92, 59.80, 58.60, 59.09, 63.00, 65.54, 63.02, 62.51, 62.84, 64.70, 64.65, 67.26, 99.61,117.41,111.12, 92.55, 61.66, 60.15, 59.35, 58.38, 57.54]
queue     = [42.80, 43.33, 43.74, 43.40, 43.54, 42.48, 43.49, 45.93, 47.80, 46.50, 46.05, 46.29, 46.89, 47.82, 48.86, 54.31, 69.43, 81.34, 64.42, 55.06, 53.45, 52.32, 50.75, 49.42]
classical = [52.36, 55.50, 55.28, 56.90, 54.18, 56.35, 51.31, 48.90, 50.21, 49.45, 48.84, 48.94, 50.06, 49.16, 50.68, 52.35, 56.97, 68.70, 52.27, 48.42, 50.23, 52.33, 55.19, 54.94]

results_file = (
    Path(__file__).resolve().parents[2]
    / "seattle_quantum_data"
    / "quantum_simulation_results.json"
)
with results_file.open(encoding="utf-8") as file:
    quantum_results = json.load(file)

hourly_summary = quantum_results["hourly_summary"]
if len(hourly_summary) != len(hours):
    raise ValueError(
        f"Expected {len(hours)} hourly Seattle results, found {len(hourly_summary)}."
    )

quantum_stats = [
    hour["statistics"]["average_travel_time"] for hour in hourly_summary
]
quantum = np.array([stats["mean"] for stats in quantum_stats])
quantum_std = np.array([stats["standard_deviation"] for stats in quantum_stats])
quantum_min = np.array([stats["min"] for stats in quantum_stats])
quantum_max = np.array([stats["max"] for stats in quantum_stats])

quantum_color = "tab:red"

plt.figure()

plt.fill_between(
    hours,
    quantum_min,
    quantum_max,
    color=quantum_color,
    alpha=0.08,
    label="QAOA Optimization min-max",
)
plt.fill_between(
    hours,
    quantum - 2 * quantum_std,
    quantum + 2 * quantum_std,
    color=quantum_color,
    alpha=0.12,
    label="QAOA Optimization +/- 2 SD",
)
plt.fill_between(
    hours,
    quantum - quantum_std,
    quantum + quantum_std,
    color=quantum_color,
    alpha=0.22,
    label="QAOA Optimization +/- 1 SD",
)

plt.plot(hours, fixed, color="tab:blue", linewidth=1.6, label="Fixed-Time")
plt.plot(hours, queue, color="tab:orange", linewidth=1.6, label="Queue-Based")
plt.plot(
    hours,
    classical,
    color="tab:green",
    linewidth=1.6,
    label="Classical Optimization",
)
plt.plot(
    hours,
    quantum,
    color=quantum_color,
    linewidth=1.6,
    label="QAOA Optimization",
)

plt.scatter(hours, fixed, color="tab:blue", s=20)
plt.scatter(hours, queue, color="tab:orange", s=20)
plt.scatter(hours, classical, color="tab:green", s=20)
plt.scatter(hours, quantum, color=quantum_color, s=20)

plt.xlabel("Hour of Day")
plt.ylabel("Average Travel Time (s)")
plt.title("Travel Time vs Hour of Day")

plt.xticks(hours)
plt.xlim(0, 23)

plt.legend()
plt.grid()

plt.show()
