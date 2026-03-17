import dimod
from dimod import BinaryQuadraticModel
from dimod.reference.samplers import SimulatedAnnealingSampler

# Simple QUBO:
# Minimize: -3x1 - 2x2 + 4x1x2

Q = {
    ('x1', 'x1'): -3,
    ('x2', 'x2'): -2,
    ('x1', 'x2'): 4
}

bqm = BinaryQuadraticModel.from_qubo(Q)

sampler = SimulatedAnnealingSampler()
sampleset = sampler.sample(bqm, num_reads=100)

print(sampleset.first)