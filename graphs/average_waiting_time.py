import matplotlib.pyplot as plt
from scipy.interpolate import make_interp_spline
import numpy as np

alpha = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]

fixed =     [44.43, 44.98, 44.27, 46.04, 45.21, 45.29, 48.31, 44.97, 45.97, 40.53, 39.47]
queue =     [32.48, 32.19, 31.88, 31.83, 34.24, 37.86, 43.02, 41.51, 41.97, 38.49, 38.82]
classical = [29.43, 29.22, 28.43, 29.43, 29.3, 32.99, 39.04, 40.2, 37.15, 37.32, 36.97]
quantum =   [30.8, 30.93, 29, 30.48, 31.83, 32.26, 38.91, 39.73, 41.43, 42.15, 43.12]

alpha_smooth = np.linspace(min(alpha), max(alpha), 1000)

fixed_smooth = make_interp_spline(alpha, fixed)(alpha_smooth)
queue_smooth = make_interp_spline(alpha, queue)(alpha_smooth)
classical_smooth = make_interp_spline(alpha, classical)(alpha_smooth)
quantum_smooth = make_interp_spline(alpha, quantum)(alpha_smooth)

plt.figure()

plt.plot(alpha_smooth, fixed_smooth, linewidth=2.5, label='Fixed')
plt.plot(alpha_smooth, queue_smooth, linewidth=2.5, label='Queue')
plt.plot(alpha_smooth, classical_smooth, linewidth=2.5, label='Classical')
plt.plot(alpha_smooth, quantum_smooth, linewidth=2.5, label='Quantum')

plt.scatter(alpha, fixed, s=50)
plt.scatter(alpha, queue, s=50)
plt.scatter(alpha, classical, s=50)
plt.scatter(alpha, quantum, s=50)

plt.xlabel('Probability of Straight (α)')
plt.ylabel('Average Waiting Time (s)')
plt.title('Waiting Time vs Probability of Straight (α)')

plt.ylim(15, 70)

plt.gca().invert_yaxis()

plt.legend()
plt.grid()

plt.show()