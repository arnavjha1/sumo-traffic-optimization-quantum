from quantum_tls import solve_tls_phases

queues = {
    "NS": 15,
    "EW": 4
}

phase = solve_tls_phases(queues)
print("Chosen phase:", phase)
