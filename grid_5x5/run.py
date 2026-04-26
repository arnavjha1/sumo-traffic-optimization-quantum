import os
import sys
import random

# ---- SUMO setup ----
if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
    sys.exit("SUMO_HOME not set")

import traci
import random

sumo_cmd = [
    "sumo",
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

import random

while traci.simulation.getMinExpectedNumber() > 0:
    traci.simulationStep()

    for vid in traci.vehicle.getIDList():

        current_edge = traci.vehicle.getRoadID(vid)

        # skip if not on a normal edge
        if ":" in current_edge:
            continue

        # get outgoing edges from current edge
        next_edges = traci.edge.getOutgoing(current_edge)

        if not next_edges:
            continue

        # enforce minimum structure assumption
        if len(next_edges) < 3:
            continue  # skip weird junctions for now

        # 60/20/20 decision
        r = random.random()

        if r < 0.6:
            target = next_edges[0]      # straight (assumed)
        elif r < 0.8:
            target = next_edges[1]      # left (assumed)
        else:
            target = next_edges[2]      # right (assumed)

        # force movement
        traci.vehicle.changeTarget(vid, target)


traci.close()