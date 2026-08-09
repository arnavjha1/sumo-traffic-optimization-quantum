import numpy as np

LAMBDA = 10


def quantum_decision(
    biases,
    prev_state,
    neighbors,
    coupling_strength=2,
    p=1,
):

    biases = np.asarray(biases, dtype=float)
    prev_state = np.asarray(prev_state, dtype=int)

    n = len(biases)

    if n == 0:
        return ""

    if len(prev_state) != n:
        raise ValueError("biases and prev_state must have the same length")

    if len(neighbors) != n:
        raise ValueError("neighbors must contain one entry per intersection")

    if not np.all(np.isin(prev_state, [0, 1])):
        raise ValueError("prev_state must contain only 0 and 1")

    # Convert previous binary state into Ising spin state:
    # 0 -> -1, 1 -> +1
    prev_spin = 2 * prev_state - 1

    # Effective field used by both the traffic-bias and switching-penalty terms.
    effective_biases = biases + LAMBDA * prev_spin

    # Build a unique list of undirected edges so each coupling is counted once.
    edges = []
    for i in range(n):
        for j in neighbors[i]:
            if not 0 <= j < n:
                raise ValueError(f"neighbor index {j} is out of range")
            if i < j:
                edges.append((i, j))

    def calculate_energy(spins):
        """Evaluate the same Ising objective used by the quantum version."""

        energy = -float(np.dot(effective_biases, spins))

        for i, j in edges:
            energy += -coupling_strength * spins[i] * spins[j]

        return energy

    # Starting from the previous state is appropriate for a traffic controller
    # and keeps the switching penalty meaningful from the first step.
    current_spin = prev_spin.copy()
    current_energy = calculate_energy(current_spin)

    best_spin = current_spin.copy()
    best_energy = current_energy

    # Classical simulated-annealing settings.
    # These are internal constants so the external function interface remains
    # identical to the quantum implementation.
    num_restarts = 8
    iterations_per_restart = 512
    initial_temperature = 5.0
    final_temperature = 0.01

    rng = np.random.default_rng()

    for restart in range(num_restarts):

        # First restart begins at the previous traffic state. Later restarts use
        # random states to reduce dependence on a single starting configuration.
        if restart == 0:
            current_spin = prev_spin.copy()
        else:
            current_spin = rng.choice([-1, 1], size=n)

        current_energy = calculate_energy(current_spin)

        if current_energy < best_energy:
            best_spin = current_spin.copy()
            best_energy = current_energy

        for step in range(iterations_per_restart):

            progress = step / max(iterations_per_restart - 1, 1)

            # Exponential cooling schedule.
            temperature = initial_temperature * (
                final_temperature / initial_temperature
            ) ** progress

            # Propose a neighboring solution by flipping one signal state.
            flip_index = int(rng.integers(0, n))
            candidate_spin = current_spin.copy()
            candidate_spin[flip_index] *= -1

            candidate_energy = calculate_energy(candidate_spin)
            delta_energy = candidate_energy - current_energy

            # Always accept lower-energy states. At nonzero temperature,
            # occasionally accept higher-energy states to escape local minima.
            if delta_energy <= 0:
                accept = True
            else:
                acceptance_probability = np.exp(
                    -delta_energy / max(temperature, 1e-12)
                )
                accept = rng.random() < acceptance_probability

            if accept:
                current_spin = candidate_spin
                current_energy = candidate_energy

                if current_energy < best_energy:
                    best_spin = current_spin.copy()
                    best_energy = current_energy

    # Convert Ising spins back into the original binary bitstring format:
    # -1 -> 0, +1 -> 1
    best_binary = ((best_spin + 1) // 2).astype(int)
    best_bitstring = "".join(str(bit) for bit in best_binary)

    return best_bitstring
