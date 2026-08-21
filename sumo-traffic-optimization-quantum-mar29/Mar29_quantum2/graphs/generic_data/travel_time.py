# GENERIC DATA - TRAVEL TIME DATA
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

alpha = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
#              0.0     0.1     0.2     0.3     0.4     0.5     0.6     0.7    0.8    0.9     1.0
fixed =     [105.85, 107.95, 105.65, 108.48, 108.78, 107.73, 112.06, 104.49, 98.41, 82.94,  72.19]
classical = [ 79.79,  79.79,  79.82,  82.11,  85.76, 100.28,  99.96,  99.54, 84.46, 84.61,  86.24]
o_quantum = [ 81.59,  81.77,  80.41,  83.04,  88.41,  91.45,  92.47,  98.08, 95.97, 95.91, 101.45]
mplight =   [ 82.95,  84.62,  85.32,  87.94,  90.54,  99.18, 100.80,  96.73, 83.06, 86.80,  88.42]
presslight = [ 83.47,  84.44,  84.40,  88.15,  91.86, 103.03,  99.04,  94.97, 89.51, 87.59,  89.44]

results_file = (
    Path(__file__).resolve().parents[2]
    / 'generic_quantum_data'
    / 'quantum_simulation_results.json'
)
with results_file.open(encoding='utf-8') as file:
    quantum_results = json.load(file)

quantum_stats = [
    quantum_results[f'3_quantum_a{i}']['statistics']['average_travel_time']
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
plt.ylabel('Average Travel Time (s)')
plt.title('Travel Time vs Probability of Straight (α)')

plt.ylim(50, 150)

plt.gca().invert_yaxis()

plt.legend()
plt.grid()

plt.show()
