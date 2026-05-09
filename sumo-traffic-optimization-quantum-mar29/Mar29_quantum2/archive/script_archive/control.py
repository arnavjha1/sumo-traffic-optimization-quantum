import traci
import sys

SUMO_BINARY = "sumo-gui"   # we can change to "sumo" if we want to clearly see logs
CONFIG = "grid.sumocfg"

traci.start([SUMO_BINARY, "-c", CONFIG])

tls_ids = traci.trafficlight.getIDList()
print("Traffic lights:", len(tls_ids))

# Put all lights into manual control
for tls in tls_ids:
    traci.trafficlight.setProgram(tls, "0")

step = 0
while traci.simulation.getMinExpectedNumber() > 0:
    phase = (step // 30) % 2   # Basic 30-step phase change (Algorithm #1)

    for tls in tls_ids:
        traci.trafficlight.setPhase(tls, phase)

    traci.simulationStep()
    step += 1

traci.close()
