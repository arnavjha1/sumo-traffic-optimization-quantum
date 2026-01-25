import traci

SUMO_BINARY = "sumo-gui"
SUMO_CONFIG = "sim.sumocfg"

PHASE_DURATION = 30
END_TIME = 600

traci.start([SUMO_BINARY, "-c", SUMO_CONFIG])

tls_ids = traci.trafficlight.getIDList()
print("Traffic lights found:", tls_ids)

# Cache phase counts (IMPORTANT)
phase_counts = {}

for tls in tls_ids:
    logic = traci.trafficlight.getAllProgramLogics(tls)[0]
    phase_counts[tls] = len(logic.phases)
    traci.trafficlight.setPhase(tls, 0)

while traci.simulation.getTime() < END_TIME:
    traci.simulationStep()
    t = int(traci.simulation.getTime())

    if t > 0 and t % PHASE_DURATION == 0:
        for tls in tls_ids:
            current = traci.trafficlight.getPhase(tls)
            next_phase = (current + 1) % phase_counts[tls]
            traci.trafficlight.setPhase(tls, next_phase)

traci.close()
