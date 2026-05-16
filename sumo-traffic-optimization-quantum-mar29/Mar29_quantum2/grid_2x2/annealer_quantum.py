from qiskit import QuantumCircuit
from qiskit.primitives import StatevectorSampler
import numpy as np

LAMBDA = 20

def quantum_decision(biases, prev_state, p=1):

    n = len(biases)

    # Effective biases including switching penalty
    effective_biases = []

    for i in range(n):

        # prev_state should be 0 or 1
        penalty = LAMBDA * (1 - 2 * prev_state[i])

        effective_biases.append(
            biases[i] - penalty
        )

    gammas = np.linspace(0, np.pi, 10)
    betas = np.linspace(0, np.pi/2, 10)

    best_energy = float("inf")
    best_bitstring = None

    sampler = StatevectorSampler()

    for gamma in gammas:
        for beta in betas:

            qc = QuantumCircuit(n)

            # Superposition
            qc.h(range(n))

            # COST UNITARY
            for i in range(n):
                qc.rz(
                    2 * gamma * effective_biases[i],
                    i
                )

            # MIXER
            for i in range(n):
                qc.rx(2 * beta, i)

            qc.measure_all()

            result = sampler.run([qc], shots=512).result()
            counts = result[0].data.meas.get_counts()

            for bitstring, freq in counts.items():

                bitstring = bitstring[::-1]

                x = np.array([
                    1 if b == '1' else 0
                    for b in bitstring
                ])

                # TRUE ENERGY
                energy = 0

                for i in range(n):

                    energy += -biases[i] * x[i]

                    energy += LAMBDA * (
                        x[i] - prev_state[i]
                    )**2

                if energy < best_energy:
                    best_energy = energy
                    best_bitstring = bitstring

    return best_bitstring