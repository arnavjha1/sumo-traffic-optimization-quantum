from qiskit import QuantumCircuit
from qiskit.primitives import StatevectorSampler

import matplotlib.pyplot as plt
from qiskit.visualization import plot_histogram

qc = QuantumCircuit(2)
qc.h(0)
qc.cx(0, 1)
qc.measure_all()

sampler = StatevectorSampler()
result = sampler.run([qc], shots=1024).result()
print(result[0].data.meas.get_counts())


counts = result[0].data.meas.get_counts()
plot_histogram(counts)

plt.show()