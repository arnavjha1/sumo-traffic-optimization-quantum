import os
import sys
import traci
import random

tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
sys.path.append(tools)

meta_data = [
    "sumo-gui",
    "-n", "grid_5x5/grid5x5_tls.net.xml",
    "-r", "grid_5x5/routes.rou.xml",
    "--step-length", "1"
]

traci.start(meta_data)

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

        if lane_id.startswith(":"):
            continue

        edge = traci.vehicle.getRoadID(vid)
        num_lanes = traci.edge.getLaneNumber(edge)

        if vid not in last_edge or last_edge[vid] != edge:

            direction = choose_direction()
            target_lane = LANE_MAP[direction]

            # clamp safely
            target_lane = max(0, min(target_lane, num_lanes - 1))

            try:
                traci.vehicle.changeLane(vid, target_lane, 100)
            except:
                pass

        last_edge[vid] = edge

traci.close()