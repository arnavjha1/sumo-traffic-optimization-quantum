import traci

SUMO_BINARY = "C:\Program Files (x86)\Eclipse\Sumo\bin\sumo.exe"
SUMO_CONFIG = "sim.sumocfg"

traci.start([
    SUMO_BINARY,
    "-c", SUMO_CONFIG,
    "--start"
])

print("CONNECTED")
for _ in range(10):
    traci.simulationStep()

traci.close()
print("DONE")
