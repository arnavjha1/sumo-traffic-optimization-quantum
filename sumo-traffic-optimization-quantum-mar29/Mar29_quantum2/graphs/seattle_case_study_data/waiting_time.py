import matplotlib.pyplot as plt

hours = list(range(24))

# Enter 24 average waiting time values, one for each hour 0-23.
fixed = [None] * 24
queue = [13.71, 14.08, 12.94, 13.40, 13.53, 13.95, 31.01, 41.92, 42.13, 42.61, 41.58, 41.64, 41.90, 42.03, 42.34, 41.57, 43.04, 41.97, 41.76, 41.91, 41.87, 41.54, 41.70, 42.38]
classical = [24.50, 24.43, 23.43, 24.64, 23.88, 20.52, 20.69, 34.69, 34.77, 34.88, 34.80, 34.82, 34.77, 34.76, 34.54, 34.59, 35.31, 35.50, 35.42, 35.66, 35.40, 35.27, 36.48, 35.45]
quantum = [None] * 24

plt.figure()

plt.plot(hours, fixed, marker="o", linewidth=2.5, label="Fixed")
plt.plot(hours, queue, marker="o", linewidth=2.5, label="Queue")
plt.plot(hours, classical, marker="o", linewidth=2.5, label="Classical")
plt.plot(hours, quantum, marker="o", linewidth=2.5, label="Quantum")

plt.xlabel("Hour of Day")
plt.ylabel("Average Waiting Time (s)")
plt.title("Waiting Time vs Hour of Day")

plt.xticks(hours)
plt.xlim(0, 23)
plt.gca().invert_yaxis()

plt.legend()
plt.grid()

plt.show()
