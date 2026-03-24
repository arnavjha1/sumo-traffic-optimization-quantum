import matplotlib.pyplot as plt

alpha = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]

fixed =     [838, 831, 877, 909, 906, 852, 824, 791, 846, 895, 944]
queue =     [955, 976, 986, 1024, 1024, 708, 889, 904, 903, 905, 830]
classical = [908, 924, 949, 978, 996, 910, 938, 946, 926, 825, 763]
quantum =   [855, 871, 923, 940, 1014, 1012, 923, 927, 843, 747, 680]

plt.figure()

plt.plot(alpha, fixed, marker='o', linewidth=2.5, markersize=8, label='Fixed')
plt.plot(alpha, queue, marker='o', linewidth=2.5, markersize=8, label='Queue')
plt.plot(alpha, classical, marker='o', linewidth=2.5, markersize=8, label='Classical')
plt.plot(alpha, quantum, marker='o', linewidth=2.5, markersize=8, label='Quantum')

plt.xlabel('Probability of Straight (⍺)')
plt.ylabel('Throughput')
plt.title('Throughput vs Probability of Straight (⍺)')

plt.ylim(300, 1200)

plt.legend()
plt.grid()
plt.show()