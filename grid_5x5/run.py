import os
import sys
import traci
import random
import math

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


# ---- helper: weighted decision ----
def choose_direction():
    r = random.random()
    if r < 0.6:
        return "STRAIGHT"
    elif r < 0.8:
        return "LEFT"
    else:
        return "RIGHT"

def angle(a, b):
    return math.atan2(b[1]-a[1], b[0]-a[0])

def classify(prev_edge, candidate_edge):
    # get geometry
    a1 = traci.edge.getFromNode(prev_edge)
    a2 = traci.edge.getToNode(prev_edge)

    b1 = traci.edge.getFromNode(candidate_edge)
    b2 = traci.edge.getToNode(candidate_edge)

    v1 = traci.junction.getPosition(a2)
    v2 = traci.junction.getPosition(b2)

    v0 = traci.junction.getPosition(a1)

    ang1 = angle(v0, v2)
    ang2 = angle(v0, v1)

    diff = (ang1 - ang2) % (2*math.pi)

    if diff < 0.5 or diff > 2*math.pi - 0.5:
        return "straight"
    elif diff < math.pi:
        return "left"
    else:
        return "right"
    
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

while traci.simulation.getMinExpectedNumber() > 0:
    traci.simulationStep()

    for vid in traci.vehicle.getIDList():
        lane_id = traci.vehicle.getLaneID(vid)

        # Skip junction/internal lanes
        if lane_id.startswith(":"):
            continue

        edge_id = traci.vehicle.getRoadID(vid)

        # Choose direction probabilistically
        direction = choose_direction()
        target_lane_index = LANE_MAP[direction]

        try:
            # Change to desired lane BEFORE intersection
            traci.vehicle.changeLane(vid, target_lane_index, 50)
        except:
            pass

traci.close()