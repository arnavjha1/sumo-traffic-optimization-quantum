import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

hours = list(range(24))

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

metric_keys = {
    "Average Travel Time": "average_travel_time",
    "Average Waiting Time": "average_waiting_time",
}

std_series = {}
for label, metric_key in metric_keys.items():
    std_values = [
        hour["statistics"][metric_key]["standard_deviation"] for hour in hourly_summary
    ]
    std_series[label] = np.maximum(np.array(std_values, dtype=float), 1e-6)

plt.figure(figsize=(10, 4.8))
for label, values in std_series.items():
    color = {
        "Average Travel Time": "tab:blue",
        "Average Waiting Time": "tab:orange",
    }[label]
    plt.plot(
        hours,
        values,
        color=color,
        linewidth=2.2,
        marker="o",
        markersize=6,
        label=f"QAOA {label} std. dev.",
    )

plt.yscale("log", base=2)
plt.xlabel("Hour of Day")
plt.ylabel("QAOA Standard Deviation (log2 scale)")
plt.title("QAOA Standard Deviation vs 24 Hours")
plt.xticks(hours)
plt.grid(True, alpha=0.3, which="both")
plt.legend()
plt.tight_layout()
plt.show()
