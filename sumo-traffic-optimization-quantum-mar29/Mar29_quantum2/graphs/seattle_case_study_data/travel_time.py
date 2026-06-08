import matplotlib.pyplot as plt

hours = list(range(24))

# Enter 24 average travel time values, one for each hour 0-23.
fixed = [57.33, 59.84, 59.27, 59.92, 59.80, 58.60, 59.09, 63.00, 65.54, 63.02, 62.51, 62.84, 64.70, 64.65, 67.26, 99.61, 117.41, 111.12, 92.55, 61.66, 60.15, 59.35, 58.38, 57.54]
queue = [42.80, 43.33, 43.74, 43.40, 43.54, 42.48, 43.49, 45.93, 47.80, 46.50, 46.05, 46.29, 46.89, 47.82, 48.86, 54.31, 69.43, 81.34, 64.42, 55.06, 53.45, 52.32, 50.75, 49.42]
classical = [52.36, 55.50, 55.28, 56.90, 54.18, 56.35, 51.31, 48.90, 50.21, 49.45, 48.84, 48.94, 50.06, 49.16, 50.68, 52.35, 56.97, 68.70, 52.27, 48.42, 50.23, 52.33, 55.19, 54.94]
quantum = [52.74, 56.27, 55.06, 55.47, 54.73, 55.29, 49.05, 47.61, 48.33, 47.82, 47.79, 47.77, 47.88, 48.01, 49.08, 50.47, 53.28, 71.08, 56.95, 47.66, 48.34, 49.36, 52.41, 54.87]

plt.figure()

plt.plot(hours, fixed, marker="o", linewidth=2.5, label="Fixed")
plt.plot(hours, queue, marker="o", linewidth=2.5, label="Queue")
plt.plot(hours, classical, marker="o", linewidth=2.5, label="Classical")
plt.plot(hours, quantum, marker="o", linewidth=2.5, label="Quantum")

plt.xlabel("Hour of Day")
plt.ylabel("Average Travel Time (s)")
plt.title("Travel Time vs Hour of Day")

plt.xticks(hours)
plt.xlim(0, 23)

plt.legend()
plt.grid()

plt.show()
