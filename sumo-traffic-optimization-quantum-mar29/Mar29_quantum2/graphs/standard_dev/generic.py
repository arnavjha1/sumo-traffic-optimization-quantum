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

std_values = [
    quantum_results[f"3_quantum_a{i}"]["statistics"]["throughput"]["standard_deviation"]
    for i in range(len(alpha))
]
std_values = np.array(std_values, dtype=float)

plt.figure(figsize=(8, 4.8))
plt.plot(
    alpha,
    std_values,
    color="tab:red",
    linewidth=2.2,
    marker="o",
    markersize=7,
    label="QAOA throughput std. dev.",
)

plt.xlabel("Probability of Straight (α)")
plt.ylabel("QAOA Standard Deviation")
plt.title("QAOA Throughput Standard Deviation vs Probability of Straight (α)")
plt.xticks(alpha)
plt.grid(True, alpha=0.3)
plt.legend()
plt.tight_layout()
plt.show()
