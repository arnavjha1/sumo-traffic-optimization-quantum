# GENERIC DATA - WAITING TIME DATA
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

alpha = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
#             0.0    0.1    0.2    0.3    0.4    0.5    0.6    0.7    0.8    0.9    1.0
fixed =     [44.43, 44.98, 44.27, 46.04, 45.21, 45.29, 48.31, 44.97, 45.97, 40.53, 39.47]
classical = [29.43, 29.22, 28.43, 29.43, 29.30, 32.99, 39.04, 40.20, 37.15, 37.32, 36.97]
o_quantum = [30.80, 30.93, 29.00, 30.48, 31.83, 32.26, 38.91, 39.73, 41.43, 42.15, 43.12]
mplight =   [35.05, 36.08, 34.67, 35.60, 32.87, 34.40, 39.95, 39.45, 36.16, 37.23, 36.80]
presslight = [34.53, 34.68, 34.49, 35.75, 35.35, 36.34, 38.60, 39.28, 38.19, 37.71, 37.76]

results_file = (
    Path(__file__).resolve().parents[2]
    / 'generic_quantum_data'
    / 'quantum_simulation_results.json'
)
with results_file.open(encoding='utf-8') as file:
    quantum_results = json.load(file)

quantum_stats = [
    quantum_results[f'3_quantum_a{i}']['statistics']['average_waiting_time']
    for i in range(len(alpha))
]
quantum = np.array([stats['mean'] for stats in quantum_stats])
quantum_std = np.array([stats['standard_deviation'] for stats in quantum_stats])
quantum_min = np.array([stats['min'] for stats in quantum_stats])
quantum_max = np.array([stats['max'] for stats in quantum_stats])

plt.figure()

quantum_color = 'tab:red'
plt.fill_between(
    alpha,
    quantum_min,
    quantum_max,
    color=quantum_color,
    alpha=0.08,
    label='QAOA Optimization min-max',
)
plt.fill_between(
    alpha,
    quantum - 2 * quantum_std,
    quantum + 2 * quantum_std,
    color=quantum_color,
    alpha=0.12,
    label='QAOA Optimization +/- 2 SD',
)
plt.fill_between(
    alpha,
    quantum - quantum_std,
    quantum + quantum_std,
    color=quantum_color,
    alpha=0.22,
    label='QAOA Optimization +/- 1 SD',
)

plt.plot(alpha, fixed, color='tab:blue', linewidth=2.5, label='Fixed-Time')
plt.plot(alpha, classical, color='tab:green', linewidth=2.5, label='Classical Optimization')
plt.plot(alpha, mplight, color='tab:purple', linewidth=2.5, label='MPLight')
plt.plot(alpha, presslight, color='tab:brown', linewidth=2.5, label='PressLight')
plt.plot(
    alpha,
    quantum,
    color=quantum_color,
    linewidth=2.5,
    label='QAOA Optimization',
)

plt.scatter(alpha, fixed, s=50, color='tab:blue')
plt.scatter(alpha, classical, s=50, color='tab:green')
plt.scatter(alpha, mplight, s=50, color='tab:purple')
plt.scatter(alpha, presslight, s=50, color='tab:brown')
plt.scatter(alpha, quantum, s=50, color=quantum_color)

plt.xlabel('Probability of Straight (α)')
plt.ylabel('Average Waiting Time (s)')
plt.title('Waiting Time vs Probability of Straight (α)')

plt.ylim(15, 70)

plt.gca().invert_yaxis()

plt.legend()
plt.grid()

plt.show()
