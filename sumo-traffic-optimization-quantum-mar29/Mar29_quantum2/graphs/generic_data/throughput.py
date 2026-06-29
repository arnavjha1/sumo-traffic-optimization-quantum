# GENERIC DATA - THROUGHPUT DATA
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

alpha = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]

#              0.0   0.1   0.2   0.3   0.4   0.5   0.6   0.7   0.8   0.9   1.0
fixed =      [ 838,  831,  877,  909,  906,  852,  824,  791,  846,  895,  944]
queue =      [ 955,  976,  986, 1024, 1024,  708,  889,  904,  903,  905,  830]
classical =  [ 908,  924,  949,  978,  996,  910,  938,  946,  926,  825,  763]
o_quantum =  [ 855,  871,  923,  940, 1014, 1012,  923,  927,  843,  747,  680]

results_file = (
    Path(__file__).resolve().parents[2]
    / 'generic_quantum_data'
    / 'quantum_simulation_results.json'
)
with results_file.open(encoding='utf-8') as file:
    quantum_results = json.load(file)

quantum_stats = [
    quantum_results[f'3_quantum_a{i}']['statistics']['throughput']
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
plt.plot(alpha, queue, color='tab:orange', linewidth=2.5, label='Queue-Based')
plt.plot(alpha, classical, color='tab:green', linewidth=2.5, label='Classical Optimization')
plt.plot(
    alpha,
    quantum,
    color=quantum_color,
    linewidth=2.5,
    label='QAOA Optimization',
)

plt.scatter(alpha, fixed, s=50, color='tab:blue')
plt.scatter(alpha, queue, s=50, color='tab:orange')
plt.scatter(alpha, classical, s=50, color='tab:green')
plt.scatter(alpha, quantum, s=50, color=quantum_color)

plt.xlabel('Probability of Straight (⍺)')
plt.ylabel('Throughput')
plt.title('Throughput vs Probability of Straight (⍺)')

plt.ylim(300, 1200)

plt.legend()
plt.grid()

plt.show()
