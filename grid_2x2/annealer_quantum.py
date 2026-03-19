from qiskit import QuantumCircuit
from qiskit.primitives import StatevectorSampler
import numpy as np


def quantum_decision(biases):
    """
    biases: list of 4 values (one per TLS)
    returns: best bitstring (e.g., "1100")
    """

    NUM_TLS = len(biases)

    qc = QuantumCircuit(NUM_TLS)

    # =========================================
    # STEP 1: Encode biases into qubits
    # =========================================
    for i in range(NUM_TLS):
        theta = (np.tanh(biases[i]) + 1) * (np.pi / 2)
        qc.ry(theta, i)

    # =========================================
    # STEP 2: Add neighbor coupling
    # (simple chain for now)
    # =========================================
    for i in range(NUM_TLS - 1):
        qc.cx(i, i + 1)

    # =========================================
    # STEP 3: Measure
    # =========================================
    qc.measure_all()

    # Run circuit
    sampler = StatevectorSampler()
    result = sampler.run([qc], shots=1024).result()

    counts = result[0].data.meas.get_counts()

    # =========================================
    # STEP 4: Pick best configuration
    # =========================================
    best_bitstring = max(counts, key=counts.get)

    # Fix ordering
    best_bitstring = best_bitstring[::-1]

    return best_bitstring


# =========================================
# TEST BLOCK (so you can still run file)
# =========================================
if __name__ == "__main__":
    test_biases = [2.0, -1.0, 0.5, -3.0]

    result = quantum_decision(test_biases)

    print("Test biases:", test_biases)
    print("Quantum decision:", result)