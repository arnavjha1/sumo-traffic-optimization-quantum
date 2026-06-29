# SEATTLE CASE STUDY - WAITING TIME DATA
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


hours = list(range(24))

fixed = [26.24, 27.64, 27.75, 27.56, 27.72, 27.23, 27.42, 29.64, 30.67, 29.42, 29.18, 29.47, 30.25, 30.11, 31.68, 41.18, 47.05, 45.36, 40.18, 28.97, 27.88, 27.52, 26.87, 26.50]
queue = [13.57, 13.63, 14.14, 13.72, 13.89, 13.29, 13.82, 15.56, 16.81, 15.89, 15.60, 15.84, 16.26, 16.95, 17.63, 21.38, 30.84, 37.84, 27.51, 21.66, 20.59, 19.90, 18.85, 18.00]
classical = [22.34, 24.21, 24.55, 25.61, 23.58, 25.16, 20.15, 16.46, 17.10, 16.81, 16.61, 16.44, 16.92, 16.49, 17.41, 18.28, 21.04, 28.53, 18.29, 16.61, 18.74, 21.03, 24.04, 24.03]

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
    hour["statistics"]["average_waiting_time"] for hour in hourly_summary
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
plt.ylabel("Average Waiting Time (s)")
plt.title("Waiting Time vs Hour of Day")

plt.xticks(hours)
plt.xlim(0, 23)

plt.legend()
plt.grid()

plt.show()
