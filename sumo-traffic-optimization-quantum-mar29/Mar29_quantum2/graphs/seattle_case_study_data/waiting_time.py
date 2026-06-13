# SEATTLE CASE STUDY - WAITING TIME DATA
import matplotlib.pyplot as plt
import numpy as np

hours = list(range(24))

# Enter 24 average waiting time values, one for each hour 0-23.
fixed = [26.24, 27.64, 27.75, 27.56, 27.72, 27.23, 27.42, 29.64, 30.67, 29.42, 29.18, 29.47, 30.25, 30.11, 31.68, 41.18, 47.05, 45.36, 40.18, 28.97, 27.88, 27.52, 26.87, 26.50]
queue = [13.57, 13.63, 14.14, 13.72, 13.89, 13.29, 13.82, 15.56, 16.81, 15.89, 15.60, 15.84, 16.26, 16.95, 17.63, 21.38, 30.84, 37.84, 27.51, 21.66, 20.59, 19.90, 18.85, 18.00]
classical = [22.34, 24.21, 24.55, 25.61, 23.58, 25.16, 20.15, 16.46, 17.10, 16.81, 16.61, 16.44, 16.92, 16.49, 17.41, 18.28, 21.04, 28.53, 18.29, 16.61, 18.74, 21.03, 24.04, 24.03]
quantum = [22.29, 24.38, 23.74, 23.74, 23.55, 23.98, 17.93, 15.18, 15.24, 15.26, 15.45, 15.24, 15.17, 15.06, 15.67, 16.34, 17.90, 28.35, 20.10, 15.60, 16.73, 18.14, 21.40, 23.68]

colors = {
    "Fixed": "indigo",
    "Queue": "green",
    "Classical": "darkorange",
    "Quantum": "magenta",
}

smooth_hours = np.linspace(min(hours), max(hours), 300)


def smooth(values):
    x = np.array(hours, dtype=float)
    y = np.array(values, dtype=float)
    smoothed = []

    for x_new in smooth_hours:
        i = np.searchsorted(x, x_new) - 1
        i = max(0, min(i, len(x) - 2))

        p0 = y[max(i - 1, 0)]
        p1 = y[i]
        p2 = y[i + 1]
        p3 = y[min(i + 2, len(y) - 1)]
        t = (x_new - x[i]) / (x[i + 1] - x[i])

        smoothed.append(
            0.5
            * (
                (2 * p1)
                + (-p0 + p2) * t
                + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t**2
                + (-p0 + 3 * p1 - 3 * p2 + p3) * t**3
            )
        )

    return smoothed


def plot_series(values, label):
    plt.plot(smooth_hours, smooth(values), color=colors[label], linewidth=1.6, label=label)
    plt.plot(hours, values, color="black", linestyle="none", marker="o", markersize=3.5)


plt.figure()

plot_series(fixed, "Fixed")
plot_series(queue, "Queue")
plot_series(classical, "Classical")
plot_series(quantum, "Quantum")

plt.xlabel("Hour of Day")
plt.ylabel("Average Waiting Time (s)")
plt.title("Waiting Time vs Hour of Day")

plt.xticks(hours)
plt.xlim(0, 23)

plt.legend()
plt.grid()

plt.show()
