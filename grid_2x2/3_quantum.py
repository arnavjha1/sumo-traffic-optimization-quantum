from qiskit import QuantumCircuit
from qiskit.primitives import StatevectorSampler
from qiskit.visualization import plot_histogram
import matplotlib.pyplot as plt


def run_4_tls_quantum():
    NUM_TLS = 4

    qc = QuantumCircuit(NUM_TLS)

    # Step 1: Put ALL TLS into superposition
    for i in range(NUM_TLS):
        qc.h(i)

    # Step 2: Add simple neighbor coupling (chain for now)
    for i in range(NUM_TLS - 1):
        qc.cx(i, i + 1)

    # Step 3: Measure
    qc.measure_all()

    # Run simulation
    sampler = StatevectorSampler()
    result = sampler.run([qc], shots=1024).result()

    counts = result[0].data.meas.get_counts()

    print("Measurement Results:", counts)

    plot_histogram(counts)
    plt.show()


if __name__ == "__main__":
    run_4_tls_quantum()