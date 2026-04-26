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

        # skip internal lanes (junctions)
        if lane_id.startswith(":"):
            continue

        edge = traci.vehicle.getRoadID(vid)

        # only decide when entering a NEW edge
        if vid not in last_edge or last_edge[vid] != edge:
            direction = choose_direction()
            target_lane = LANE_MAP[direction]

            best_lanes = traci.vehicle.getBestLanes(vid)

            allowed_lanes = [lane[0].split("_")[-1] for lane in best_lanes]
            allowed_lanes = [int(l) for l in allowed_lanes if l.isdigit()]

            print("Chosen:", target_lane)
            print("Allowed:", allowed_lanes)

            if target_lane in allowed_lanes:
                traci.vehicle.changeLane(vid, target_lane, 100)
        
        last_edge[vid] = edge

traci.close()