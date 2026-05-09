import matplotlib.pyplot as plt
from scipy.interpolate import make_interp_spline
import numpy as np

alpha = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]

fixed =     [838, 831, 877, 909, 906, 852, 824, 791, 846, 895, 944]
queue =     [955, 976, 986, 1024, 1024, 708, 889, 904, 903, 905, 830]
classical = [908, 924, 949, 978, 996, 910, 938, 946, 926, 825, 763]
quantum =   [855, 871, 923, 940, 1014, 1012, 923, 927, 843, 747, 680]

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

plt.xlabel('Probability of Straight (⍺)')
plt.ylabel('Throughput')
plt.title('Throughput vs Probability of Straight (⍺)')

plt.ylim(300, 1200)

plt.legend()
plt.grid()

plt.show()