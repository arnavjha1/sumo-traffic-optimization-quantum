import time
import numpy as np

LAMBDA = 10


def stochastic_decision(
    biases,
    prev_state,
    neighbors,
    coupling_strength=2,
    *,
    rng,
    evaluation_budget=512,
    restarts=8,
    initial_temperature=5.0,
    final_temperature=0.01,
    return_metadata=False,
):
    """Budget-limited classical simulated annealing.

    Returns states in intersection order; no Qiskit bit reversal.
    Each restart initialization counts as one energy evaluation.
    Equal-energy best states retain the first encountered state.
    """
    started = time.perf_counter()

    biases = np.asarray(biases, dtype=float)
    previous = np.asarray(prev_state)

    if biases.ndim != 1 or len(biases) == 0:
        raise ValueError("biases must be a nonempty one-dimensional array")
    if previous.shape != biases.shape:
        raise ValueError("prev_state must match biases")
    if not np.all(np.isin(previous, [0, 1])):
        raise ValueError("prev_state must contain only 0 and 1")
    if not np.all(np.isfinite(biases)):
        raise ValueError("biases must be finite")

    n = len(biases)

    if len(neighbors) != n:
        raise ValueError("neighbors must contain one entry per intersection")
    if not isinstance(evaluation_budget, (int, np.integer)):
        raise ValueError("evaluation_budget must be an integer")
    if not isinstance(restarts, (int, np.integer)):
        raise ValueError("restarts must be an integer")
    if not 1 <= restarts <= evaluation_budget:
        raise ValueError("Require 1 <= restarts <= evaluation_budget")
    if not np.isfinite(coupling_strength):
        raise ValueError("coupling_strength must be finite")
    if not (
        np.isfinite(initial_temperature)
        and np.isfinite(final_temperature)
        and 0 < final_temperature <= initial_temperature
    ):
        raise ValueError("Require 0 < final_temperature <= initial_temperature")

    # Preserve the pasted QAOA evaluator's edge-counting convention.
    edges = []
    for i, adjacent in enumerate(neighbors):
        for j in adjacent:
            if not isinstance(j, (int, np.integer)) or not 0 <= j < n:
                raise ValueError("Neighbor indices must be valid integers")
            if i < j:
                edges.append((i, j))

    previous_spins = 2 * previous.astype(int) - 1
    effective_biases = biases + LAMBDA * previous_spins

    def energy(spins):
        value = -float(np.dot(effective_biases, spins))
        for i, j in edges:
            value -= coupling_strength * spins[i] * spins[j]
        return float(value)

    best_spins = None
    best_energy = float("inf")
    evaluations = 0
    accepted_moves = 0
    proposed_moves = 0

    # Distribute the full budget across restarts, including initialization.
    base_budget, extra = divmod(evaluation_budget, restarts)

    for restart in range(restarts):
        restart_budget = base_budget + int(restart < extra)

        if restart == 0:
            current = previous_spins.copy()
        else:
            current = rng.choice([-1, 1], size=n)

        current_energy = energy(current)
        evaluations += 1

        if current_energy < best_energy:
            best_energy = current_energy
            best_spins = current.copy()

        proposals = restart_budget - 1

        for step in range(proposals):
            progress = step / max(proposals - 1, 1)
            temperature = np.exp(
                (1 - progress) * np.log(initial_temperature)
                + progress * np.log(final_temperature)
            )

            candidate = current.copy()
            index = int(rng.integers(n))
            candidate[index] *= -1

            candidate_energy = energy(candidate)
            evaluations += 1
            proposed_moves += 1
            delta = candidate_energy - current_energy

            if delta <= 0 or rng.random() < np.exp(-delta / temperature):
                current = candidate
                current_energy = candidate_energy
                accepted_moves += 1

            if candidate_energy < best_energy:
                best_energy = candidate_energy
                best_spins = candidate.copy()

    bitstring = "".join(str(int((spin + 1) // 2)) for spin in best_spins)

    metadata = {
        "optimizer": "simulated_annealing",
        "selected_energy": best_energy,
        "energy_evaluations": evaluations,
        "proposed_moves": proposed_moves,
        "accepted_moves": accepted_moves,
        "restarts": int(restarts),
        "initial_temperature": float(initial_temperature),
        "final_temperature": float(final_temperature),
        "runtime_seconds": time.perf_counter() - started,
        "tie_breaking": "first_encountered",
    }

    if return_metadata:
        return bitstring, metadata
    return bitstring