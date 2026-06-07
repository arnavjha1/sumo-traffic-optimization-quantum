import matplotlib.pyplot as plt

hours = list(range(24))

# Enter 24 throughput values, one for each hour 0-23.
fixed = [1944, 1322, 1006, 800, 1200, 2869, 5503, 5474, 5207, 5166, 5061, 5659, 5413, 5310, 5348, 5474, 5476, 5625, 5593, 5712, 5464, 5400, 5229, 5254]
queue = [1952, 1316, 1008, 804, 1199, 2881, 6209, 6347, 6361, 6241, 6478, 6410, 6369, 6429, 6324, 6490, 6164, 6370, 6423, 6344, 6442, 6361, 6443, 6348]
classical = [1944, 1320, 1008, 800, 1198, 2873, 6303, 6516, 6498, 6505, 6534, 6496, 6551, 6524, 6507, 6507, 6521, 6470, 6541, 6477, 6465, 6548, 6379, 6459]
quantum = [None] * 24

plt.figure()

plt.plot(hours, fixed, marker="o", linewidth=2.5, label="Fixed")
plt.plot(hours, queue, marker="o", linewidth=2.5, label="Queue")
plt.plot(hours, classical, marker="o", linewidth=2.5, label="Classical")
plt.plot(hours, quantum, marker="o", linewidth=2.5, label="Quantum")

plt.xlabel("Hour of Day")
plt.ylabel("Throughput")
plt.title("Throughput vs Hour of Day")

plt.xticks(hours)
plt.xlim(0, 23)

plt.legend()
plt.grid()

plt.show()
