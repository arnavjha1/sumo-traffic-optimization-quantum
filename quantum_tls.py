import traci
import dimod
from collections import defaultdict

SUMO_BINARY = "sumo-gui"
SUMO_CONFIG = "sim.sumocfg"
END_TIME = 600
CONTROL_INTERVAL = 30  # seconds

# -----------------------
# START SUMO
# -----------------------
traci.start([SUMO_BINARY, "-c", SUMO_CONFIG])

tls_ids = traci.trafficlight.getIDList()
phase_count = {
    tls: len(traci.trafficlight.getAllProgramLogics(tls)[0].phases)
    for tls in tls_ids
}

# -----------------------
# SIMULATION LOOP
# -----------------------
while traci.simulation.getTime() < END_TIME:
    traci.simulationStep()
    t = traci.simulation.getTime()

    if t % CONTROL_INTERVAL != 0:
        continue

    # -----------------------
    # BUILD TRAFFIC STATE
    # -----------------------
    queues = {}

    for tls in tls_ids:
        q = 0
        for lane in traci.trafficlight.getControlledLanes(tls):
            for v in traci.lane.getLastStepVehicleIDs(lane):
                if traci.vehicle.getSpeed(v) < 0.1:
                    q += 1
        queues[tls] = q

    # -----------------------
    # BUILD BQM
    # -----------------------
    bqm = dimod.BinaryQuadraticModel({}, {}, 0.0, dimod.BINARY)

    for tls in tls_ids:
        for p in range(phase_count[tls]):
            var = f"{tls}_p{p}"
            # Penalize queues → prefer phases that reduce congestion
            bqm.add_variable(var, queues[tls])

        # one-hot constraint: exactly one phase
        vars_tls = [f"{tls}_p{p}" for p in range(phase_count[tls])]
        dimod.generators.combinations(bqm, vars_tls, 1, strength=50)

    # -----------------------
    # SOLVE (CLASSICAL FIRST)
    # -----------------------
    sampler = dimod.SimulatedAnnealingSampler()
    sample = sampler.sample(bqm, num_reads=50).first.sample

    # -----------------------
    # APPLY TO SUMO
    # -----------------------
    for tls in tls_ids:
        for p in range(phase_count[tls]):
            if sample.get(f"{tls}_p{p}", 0) == 1:
                traci.trafficlight.setPhase(tls, p)

traci.close()
