# SEATTLE CASE STUDY - TRAVEL TIME DATA
import matplotlib.pyplot as plt
import numpy as np

hours = list(range(24))

# Enter 24 average travel time values, one for each hour 0-23.

#             12-1    1-2    2-3    3-4    4-5    5-6    6-7    7-8    8-9   9-10  10-11  11-12   12-1    1-2    2-3    3-4    4-5    5-6    6-7    7-8    8-9   9-10  10-11  11-12
fixed     = [57.33, 59.84, 59.27, 59.92, 59.80, 58.60, 59.09, 63.00, 65.54, 63.02, 62.51, 62.84, 64.70, 64.65, 67.26, 99.61,117.41,111.12, 92.55, 61.66, 60.15, 59.35, 58.38, 57.54]
queue     = [42.80, 43.33, 43.74, 43.40, 43.54, 42.48, 43.49, 45.93, 47.80, 46.50, 46.05, 46.29, 46.89, 47.82, 48.86, 54.31, 69.43, 81.34, 64.42, 55.06, 53.45, 52.32, 50.75, 49.42]
classical = [52.36, 55.50, 55.28, 56.90, 54.18, 56.35, 51.31, 48.90, 50.21, 49.45, 48.84, 48.94, 50.06, 49.16, 50.68, 52.35, 56.97, 68.70, 52.27, 48.42, 50.23, 52.33, 55.19, 54.94]
quantum   = [52.74, 56.27, 55.06, 55.47, 54.73, 55.29, 49.05, 47.61, 48.33, 47.82, 47.79, 47.77, 47.88, 48.01, 49.08, 50.47, 53.28, 71.08, 56.95, 47.66, 48.34, 49.36, 52.41, 54.87]

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
plt.ylabel("Average Travel Time (s)")
plt.title("Travel Time vs Hour of Day")

plt.xticks(hours)
plt.xlim(0, 23)

plt.legend()
plt.grid()

plt.show()
