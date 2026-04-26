import os
import sys
import traci
import random

# ---- SUMO setup ----
if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
    sys.exit("SUMO_HOME not set")

sumo_cmd = [
    "sumo-gui",
    "-n", "grid_5x5/grid5x5_tls.net.xml",
    "-r", "grid_5x5/routes.rou.xml",
    "--step-length", "1"
]

traci.start(sumo_cmd)

# ---- probabilities ----
PROBS = {
    "straight": 0.6,
    "left": 0.2,
    "right": 0.2
}

def choose_direction():
    r = random.random()
    if r < PROBS["straight"]:
        return "straight"
    elif r < PROBS["straight"] + PROBS["left"]:
        return "left"
    else:
        return "right"

# lane mapping
LANE_MAP = {
    "right": 0,
    "straight": 1,
    "left": 2
}

# remember last edge per vehicle
last_edge = {}

while traci.simulation.getMinExpectedNumber() > 0:
    traci.simulationStep()

    for vid in traci.vehicle.getIDList():
        lane_id = traci.vehicle.getLaneID(vid)

        # skip internal lanes (junctions)
        if lane_id.startswith(":"):
            continue

        edge = traci.vehicle.getRoadID(vid)

        # only decide when entering a NEW edge
        if vid not in last_edge or last_edge[vid] != edge:
            direction = choose_direction()
            target_lane = LANE_MAP[direction]

            try:
                traci.vehicle.changeLane(vid, target_lane, 50)
            except:
                pass

        last_edge[vid] = edge

traci.close()