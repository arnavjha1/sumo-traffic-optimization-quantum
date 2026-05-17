from qiskit import QuantumCircuit
from qiskit.primitives import StatevectorSampler
import numpy as np

LAMBDA = 10
sampler = StatevectorSampler()

def quantum_decision(biases, prev_state, neighbors, coupling_strength=2, p=1):

    n = len(biases)

    # Effective biases including switching penalty
    effective_biases = []

    for i in range(n):

        # prev_state should be 0 or 1
        penalty = LAMBDA * (1 - 2 * prev_state[i])

        effective_biases.append(
            biases[i] - penalty
        )
    
    gamma = 0.5
    beta = 0.4

    best_energy = float("inf")
    best_bitstring = None

    best_gamma = None
    best_beta = None


    qc = QuantumCircuit(n)

    # Superposition
    qc.h(range(n))

    # COST UNITARY
    for i in range(n):
        qc.rz(
            2 * gamma * effective_biases[i],
            i
        )

    # Neighbor coupling
    for i in range(n):

        for j in neighbors[i]:

            # avoid duplicates
            if i < j:

                qc.cx(i, j)

                qc.rz(
                    2 * gamma * coupling_strength,
                    j
                )

                qc.cx(i, j)

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

        # TRUE ENERGY OF ENTIRE SYSTEM
        energy = 0

        for i in range(n):

            # Bias term
            energy += -biases[i] * x[i]

            # Switching penalty
            energy += LAMBDA * (
                x[i] - prev_state[i]
            )**2

            # Neighbor coupling
            for j in neighbors[i]:

                if i < j:

                    if x[i] == x[j]:

                        energy -= coupling_strength

        # Keep best sampled state overall
        if energy < best_energy:

            best_energy = energy
            best_bitstring = bitstring

    return best_bitstring