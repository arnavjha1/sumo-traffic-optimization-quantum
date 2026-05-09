import traci

SUMO_CMD = ["sumo-gui", "-c", "grid.sumocfg"]

traci.start(SUMO_CMD)

tls_ids = traci.trafficlight.getIDList()
print("TLS count:", len(tls_ids))

while traci.simulation.getTime() < 3600:
    t = traci.simulation.getTime()

    # Alternate every 30 seconds
    phase = int((t // 30) % 2)

    for tls in tls_ids:
        traci.trafficlight.setPhase(tls, phase)

    traci.simulationStep()

traci.close()
