from qiskit import QuantumCircuit
from qiskit.primitives import StatevectorSampler
import numpy as np

def quantum_decision(biases, p=1):

    n = len(biases)

    # Parameters (we'll just grid search for now)
    gammas = np.linspace(0, np.pi, 10)
    betas = np.linspace(0, np.pi/2, 10)

    best_energy = float("inf")
    best_bitstring = None

    for gamma in gammas:
        for beta in betas:

            qc = QuantumCircuit(n)

            # Initialize superposition
            qc.h(range(n))

            # ----- COST UNITARY -----
            for i in range(n):
                qc.rz(2 * gamma * biases[i], i)

            # ----- MIXER -----
            for i in range(n):
                qc.rx(2 * beta, i)

            qc.measure_all()

            sampler = StatevectorSampler()
            result = sampler.run([qc], shots=512).result()
            counts = result[0].data.meas.get_counts()

            # Evaluate classical energy
            for bitstring, freq in counts.items():
                bitstring = bitstring[::-1]
                x = np.array([1 if b == '1' else 0 for b in bitstring])

                energy = -np.dot(biases, x)

                if energy < best_energy:
                    best_energy = energy
                    best_bitstring = bitstring

    return best_bitstring