from qiskit import QuantumCircuit
from qiskit.primitives import StatevectorSampler
import numpy as np
import matplotlib.pyplot as plt  # Added for graphing

def quantum_decision(biases):
    NUM_TLS = len(biases)
    qc = QuantumCircuit(NUM_TLS)

    # STEP 1: Encode biases
    for i in range(NUM_TLS):
        theta = (np.tanh(biases[i]) + 1) * (np.pi / 2)
        qc.ry(theta, i)

    # STEP 2: Couple with neighboring traffic lights
    for i in range(NUM_TLS - 1):
        qc.cx(i, i + 1)

    # STEP 3: Measure
    qc.measure_all()

    # Run circuit
    sampler = StatevectorSampler()
    result = sampler.run([qc], shots=1024).result()
    counts = result[0].data.meas.get_counts()

    # STEP 4: Pick best configuration
    best_bitstring = max(counts, key=counts.get)
    best_bitstring = best_bitstring[::-1]

    # Modification: Return counts dictionary so we can graph it
    return best_bitstring, counts

if __name__ == "__main__":
    # Test with varying biases to see a more interesting graph
    test_biases = [-1.0, -1.0, 1.0, -1.0]

    # Get the best string and the full distribution
    best_str, all_counts = quantum_decision(test_biases)

    print("Test biases:", test_biases)
    print("Quantum decision (Best String):", best_str)

    # --- GRAPHING SECTION ---
    
    # 1. Reverse the keys to match your logic (first qubit on the left)
    formatted_counts = {k[::-1]: v for k, v in all_counts.items()}
    
    # 2. Sort the bitstrings alphabetically for a clean x-axis
    sorted_bits = sorted(formatted_counts.keys())
    sorted_freqs = [formatted_counts[b] for b in sorted_bits]

    # 3. Create the Bar Chart
    plt.figure(figsize=(10, 6))
    plt.bar(sorted_bits, sorted_freqs, color='skyblue', edgecolor='darkblue')
    plt.xlabel('Traffic Light Configurations', fontsize=12)
    plt.ylabel('Frequency', fontsize=12)
    plt.title('Quantum Decision', fontsize=14)
    plt.xticks(rotation=45) # Rotate labels for readability
    plt.grid(axis='y', linestyle='--', alpha=0.6)
    plt.tight_layout()
    plt.show()