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

def get_next_edges_with_dirs(vid):
    lane_id = traci.vehicle.getLaneID(vid)
    links = traci.lane.getLinks(lane_id)

    classified = {"straight": [], "left": [], "right": []}

    for link in links:
        next_lane = link[0]
        direction = link[6]  # THIS is the key

        next_edge = next_lane.split("_")[0]

        if direction == "s":
            classified["straight"].append(next_edge)
        elif direction == "l":
            classified["left"].append(next_edge)
        elif direction == "r":
            classified["right"].append(next_edge)

    return classified

while traci.simulation.getMinExpectedNumber() > 0:
    traci.simulationStep()

    for vid in traci.vehicle.getIDList():
        edge = traci.vehicle.getRoadID(vid)

        classified = get_next_edges_with_dirs(vid)

        next_edges = (
            classified["straight"] +
            classified["left"] +
            classified["right"]
        )

        if not next_edges:
            continue

        # pick based on probabilities
        r = random.random()

        if r < PROBS["straight"] and classified["straight"]:
            chosen = random.choice(classified["straight"])
        elif r < PROBS["straight"] + PROBS["left"] and classified["left"]:
            chosen = random.choice(classified["left"])
        elif classified["right"]:
            chosen = random.choice(classified["right"])
        else:
            chosen = random.choice(next_edges)

        # force route change
        traci.vehicle.changeTarget(vid, chosen)

traci.close()