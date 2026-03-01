from archive.script_archive.quantum_tls import solve_tls_phases

queues = {
    "NS": 20,
    "EW": 1
}

phase = solve_tls_phases(queues)
print("Chosen phase:", phase)
