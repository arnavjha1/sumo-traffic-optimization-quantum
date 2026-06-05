import matplotlib.pyplot as plt

hours = list(range(24))

# Enter 24 average waiting time values, one for each hour 0-23.
fixed = [None] * 24
queue = [None] * 24
classical = [None] * 24
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
