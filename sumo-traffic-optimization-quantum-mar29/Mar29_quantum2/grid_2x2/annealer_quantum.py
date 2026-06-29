from qiskit import QuantumCircuit
from qiskit.primitives import StatevectorSampler
import numpy as np

LAMBDA = 10
sampler = StatevectorSampler()

def quantum_decision(biases, prev_state, neighbors, coupling_strength=2, p=1):

    n = len(biases)

    # Convert previous binary state into Ising spin state
    prev_spin = np.array([
        2 * prev_state[i] - 1
        for i in range(n)
    ])

    # Effective biases including switching penalty
    effective_biases = []

    for i in range(n):

        # In Ising form, switching penalty acts like a field
        effective_biases.append(
            biases[i] + LAMBDA * prev_spin[i]
        )
    
    gamma = 0.5
    beta = 0.4

    best_energy = float("inf")
    best_bitstring = None

    qc = QuantumCircuit(n)

    # Superposition
    qc.h(range(n))

    # COST UNITARY: Ising bias term
    for i in range(n):
        qc.rz(
            2 * gamma * effective_biases[i],
            i
        )

    # COST UNITARY: Ising neighbor coupling
    for i in range(n):

        for j in neighbors[i]:

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

        # Convert binary x into Ising spin s
        s = 2*x - 1

        energy = 0

        for i in range(n):

            # Ising bias term:
            # same sign between bias and spin reduces energy
            energy += -biases[i] * s[i]

            # Ising switching penalty:
            # rewards staying aligned with previous spin
            energy += -LAMBDA * prev_spin[i] * s[i]

            # Ising neighbor coupling:
            # rewards neighboring spins being the same
            for j in neighbors[i]:

                if i < j:

                    energy += -coupling_strength * s[i] * s[j]

        if energy < best_energy:

            best_energy = energy
            best_bitstring = bitstring

    return best_bitstring