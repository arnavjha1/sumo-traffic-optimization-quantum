import matplotlib.pyplot as plt
from scipy.interpolate import make_interp_spline
import numpy as np

alpha = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
#              0.0     0.1     0.2     0.3     0.4     0.5     0.6     0.7    0.8    0.9     1.0
fixed =     [105.85, 107.95, 105.65, 108.48, 108.78, 107.73, 112.06, 104.49, 98.41, 82.94,  72.19]
queue =     [ 81.00,  81.94,  81.22,  82.75,  87.11, 104.13, 108.63, 100.86, 90.14, 79.44,  80.65]
classical = [ 79.79,  79.79,  79.82,  82.11,  85.76, 100.28,  99.96,  99.54, 84.46, 84.61,  86.24]
o_quantum = [ 81.59,  81.77,  80.41,  83.04,  88.41,  91.45,  92.47,  98.08, 95.97, 95.91, 101.45]
quantum =   [ 80.05,  79.73,  79.82,  81.68,  84.15,  86.89,  95.37,  97.09, 94.87, 88.50,  91.88]


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
plt.ylabel('Average Travel Time (s)')
plt.title('Travel Time vs Probability of Straight (α)')

plt.ylim(50, 150)

plt.gca().invert_yaxis()

plt.legend()
plt.grid()

plt.show()