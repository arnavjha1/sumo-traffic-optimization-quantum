# quantum_tls.py
from dimod import BinaryQuadraticModel
from dwave.samplers import SimulatedAnnealingSampler

def solve_tls_phases(queue_lengths):
    """
    queue_lengths: dict like {"NS": 12, "EW": 5}
    returns: phase string with highest priority
    """

    bqm = BinaryQuadraticModel({}, {}, 0.0, "BINARY")

    # Higher queue → lower energy → more likely selected
    for phase, q in queue_lengths.items():
        bqm.add_variable(phase, -q)

    sampler = SimulatedAnnealingSampler()
    result = sampler.sample(bqm, num_reads=100)

    sample = result.first.sample

    # pick active phase
    active = [k for k, v in sample.items() if v == 1]

    return active[0] if active else max(queue_lengths, key=queue_lengths.get)
