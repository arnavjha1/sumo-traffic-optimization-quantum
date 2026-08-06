import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

alpha = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]

results_file = (
    Path(__file__).resolve().parents[2]
    / "generic_quantum_data"
    / "quantum_simulation_results.json"
)
with results_file.open(encoding="utf-8") as file:
    quantum_results = json.load(file)

travel_std = np.array(
    [
        quantum_results[f"3_quantum_a{i}"]["statistics"]["average_travel_time"]["standard_deviation"]
        for i in range(len(alpha))
    ],
    dtype=float,
)
waiting_std = np.array(
    [
        quantum_results[f"3_quantum_a{i}"]["statistics"]["average_waiting_time"]["standard_deviation"]
        for i in range(len(alpha))
    ],
    dtype=float,
)

plt.figure(figsize=(8, 4.8))
plt.plot(
    alpha,
    travel_std,
    color="tab:blue",
    linewidth=2.2,
    marker="o",
    markersize=7,
    label="QAOA average travel time std. dev.",
)
plt.plot(
    alpha,
    waiting_std,
    color="tab:green",
    linewidth=2.2,
    marker="o",
    markersize=7,
    label="QAOA average waiting time std. dev.",
)

plt.xlabel("Probability of Straight (α)")
plt.ylabel("QAOA Standard Deviation")
plt.title("QAOA Generic Standard Deviation vs Probability of Straight (α)")
plt.xticks(alpha)
plt.grid(True, alpha=0.3)
plt.legend()
plt.tight_layout()
plt.show()
