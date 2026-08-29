from qiskit import QuantumCircuit, transpile
from qiskit.primitives import StatevectorSampler
from qiskit_aer import AerSimulator
from qiskit_aer.noise import NoiseModel, depolarizing_error
from collections import Counter
import numpy as np

LAMBDA = 10
sampler = StatevectorSampler()

noise_rng = np.random.default_rng()

def set_noise_seed(seed):
    global noise_rng
    noise_rng = np.random.default_rng(seed)

def build_depolarizing_noise_model(noise_level):
    """
    Build a synthetic depolarizing noise model.

    noise_level is the depolarizing error probability
    applied to each modeled gate.
    """
    noise_model = NoiseModel()

    # Single-qubit depolarizing error
    single_qubit_error = depolarizing_error(
        noise_level,
        1
    )

    # Two-qubit depolarizing error
    two_qubit_error = depolarizing_error(
        noise_level,
        2
    )

    noise_model.add_all_qubit_quantum_error(
        single_qubit_error,
        ["h", "rz", "rx"]
    )

    noise_model.add_all_qubit_quantum_error(
        two_qubit_error,
        ["cx"]
    )

    return noise_model

def apply_readout_noise(counts, noise_level):
    """
    Apply symmetric independent measurement error.

    Each measured qubit has probability noise_level of
    being reported as the opposite classical bit.
    """

    noisy_counts = Counter()
    for measured_bitstring, frequency in counts.items():
        for _ in range(frequency):
            noisy_bits = list(measured_bitstring)
            for i in range(len(noisy_bits)):
                if np.random.random() < noise_level:
                    noisy_bits[i] = (
                        "1"
                        if noisy_bits[i] == "0"
                        else "0"
                    )
            noisy_bitstring = "".join(noisy_bits)
            noisy_counts[noisy_bitstring] += 1

    return dict(noisy_counts)

def quantum_decision(
    biases,
    prev_state,
    neighbors,
    coupling_strength=2,
    p=1,
    shots=512,
    fixed_params=None,
    return_metadata=False,
    noise_type="none",
    noise_level=0.0
):

    n = len(biases)

    print(
        f"NOISE SETTINGS: type={noise_type}, "
        f"level={noise_level}"
    )

    # ---------------------------------------------------
    # Optional depolarizing-noise simulator
    # ---------------------------------------------------

    depolarizing_simulator = None
    if noise_type == "depolarizing" and noise_level > 0:
        print(f"DEPOLARIZING AER ACTIVE: p={noise_level}")

        noise_model = build_depolarizing_noise_model(
            noise_level
        )

        depolarizing_simulator = AerSimulator(
            noise_model=noise_model
        )

    # ---------------------------------------------------
    # Convert previous binary state into Ising spin state
    # ---------------------------------------------------
    prev_spin = np.array([
        2 * prev_state[i] - 1
        for i in range(n)
    ])

    # ---------------------------------------------------
    # Effective biases including switching penalty
    # ---------------------------------------------------
    effective_biases = []

    for i in range(n):

        effective_biases.append(
            biases[i] + LAMBDA * prev_spin[i]
        )

    # ---------------------------------------------------
    # QAOA HYPERPARAMETER SEARCH
    # ---------------------------------------------------

    if fixed_params is None:

        gamma_values = np.linspace(
            0,
            np.pi,
            10
        )

        beta_values = np.linspace(
            0,
            np.pi / 2,
            10
        )

        p_values = [1, 2]

    else:

        fixed_gamma, fixed_beta, fixed_p = fixed_params

        gamma_values = [fixed_gamma]
        beta_values = [fixed_beta]
        p_values = [fixed_p]

    # shots is supplied by the caller so shot sensitivity can be tested
    # without changing the QAOA algorithm itself.

    # ---------------------------------------------------
    # Best QAOA parameterization
    # ---------------------------------------------------

    best_expected_energy = float("inf")

    best_gamma = None
    best_beta = None
    best_p = None

    best_counts = None

    # ---------------------------------------------------
    # Energy calculation
    # ---------------------------------------------------

    def calculate_energy(bitstring):

        x = np.array([
            1 if b == "1" else 0
            for b in bitstring
        ])

        # Binary -> Ising
        s = 2 * x - 1

        energy = 0.0

        for i in range(n):

            # Traffic bias
            energy += (
                -biases[i]
                * s[i]
            )

            # Switching penalty
            energy += (
                -LAMBDA
                * prev_spin[i]
                * s[i]
            )

            # Neighbor coupling
            for j in neighbors[i]:

                if i < j:

                    energy += (
                        -coupling_strength
                        * s[i]
                        * s[j]
                    )

        return energy

    # ---------------------------------------------------
    # Classical outer-loop hyperparameter search
    # ---------------------------------------------------

    for current_p in p_values:

        for gamma in gamma_values:

            for beta in beta_values:

                # -----------------------------------
                # Build QAOA circuit
                # -----------------------------------

                qc = QuantumCircuit(n)

                # Optional QAOA angle uncertainty
                if noise_type == "angle" and noise_level > 0:
                    gamma_eff = gamma + noise_rng.normal(0.0, noise_level)
                    beta_eff = beta + noise_rng.normal(0.0, noise_level)
                else:
                    gamma_eff = gamma
                    beta_eff = beta

                # Initial superposition
                qc.h(range(n))

                # -----------------------------------
                # p QAOA layers
                # -----------------------------------

                for layer in range(current_p):

                    # -------------------------------
                    # COST UNITARY: bias terms
                    # -------------------------------

                    for i in range(n):

                        qc.rz(
                            2
                            * gamma_eff
                            * effective_biases[i],
                            i
                        )

                    # -------------------------------
                    # COST UNITARY: neighbor coupling
                    # -------------------------------

                    for i in range(n):

                        for j in neighbors[i]:

                            if i < j:

                                qc.cx(i, j)

                                qc.rz(
                                    2
                                    * gamma_eff
                                    * coupling_strength,
                                    j
                                )

                                qc.cx(i, j)

                    # -------------------------------
                    # MIXER
                    # -------------------------------

                    for i in range(n):

                        qc.rx(
                            2 * beta_eff,
                            i
                        )


                # -----------------------------------
                # Measurement
                # -----------------------------------

                qc.measure_all()

                # -----------------------------------
                # Execute quantum circuit
                # -----------------------------------

                if noise_type == "depolarizing" and noise_level > 0:

                    # Compile the circuit for Aer while preserving
                    # the gate family used by this QAOA implementation.
                    compiled_qc = transpile(
                        qc,
                        depolarizing_simulator,
                        optimization_level=0
                    )

                    result = depolarizing_simulator.run(
                        compiled_qc,
                        shots=shots
                    ).result()

                    counts = result.get_counts(
                        compiled_qc
                    )

                else:

                    # Preserve the original ideal StatevectorSampler
                    # execution for none / angle / readout experiments.
                    result = sampler.run(
                        [qc],
                        shots=shots
                    ).result()

                    counts = (
                        result[0]
                        .data
                        .meas
                        .get_counts()
                    )

                # -----------------------------------
                # Optional readout / measurement noise
                # -----------------------------------
                if noise_type == "readout" and noise_level > 0:
                    counts = apply_readout_noise(
                        counts,
                        noise_level
                    )

                # -----------------------------------
                # EXPECTED ENERGY
                # -----------------------------------
                #
                # Rank this parameter combination using:
                #
                # <E> = sum_x P(x) * E(x)
                #
                # NOT by the single best sampled state.
                # -----------------------------------

                expected_energy = 0.0

                for measured_bitstring, freq in counts.items():

                    # Reverse Qiskit bit ordering
                    bitstring = measured_bitstring[::-1]

                    energy = calculate_energy(
                        bitstring
                    )

                    probability = (
                        freq / shots
                    )

                    expected_energy += (
                        probability
                        * energy
                    )

                # -----------------------------------
                # Keep best parameter combination
                # -----------------------------------

                if expected_energy < best_expected_energy:

                    best_expected_energy = expected_energy

                    best_gamma = gamma
                    best_beta = beta
                    best_p = current_p

                    # Save samples from this specific
                    # best-performing circuit
                    best_counts = counts

    # ---------------------------------------------------
    # Select best state from BEST parameter combination
    # ---------------------------------------------------

    best_energy = float("inf")
    best_bitstring = None

    for measured_bitstring, freq in best_counts.items():

        # Reverse Qiskit bit ordering
        bitstring = measured_bitstring[::-1]

        energy = calculate_energy(
            bitstring
        )

        if energy < best_energy:

            best_energy = energy
            best_bitstring = bitstring

    # ---------------------------------------------------
    # Debug information
    # ---------------------------------------------------

    print(
        "BEST QAOA:",
        f"expected_energy={best_expected_energy:.2f}",
        f"best_sample_energy={best_energy:.2f}",
        f"gamma={best_gamma:.3f}",
        f"beta={best_beta:.3f}",
        f"p={best_p}",
        f"shots={shots}",
        f"state={best_bitstring}"
    )
    
    if return_metadata:
        return (
            best_bitstring,
            best_gamma,
            best_beta,
            best_p,
            best_expected_energy
        )

    return best_bitstring