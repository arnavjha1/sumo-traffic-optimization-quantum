import os
import sys
import traci
import random

tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
sys.path.append(tools)

traci.start([
    "sumo-gui",
    "-n", "grid_5x5/grid5x5_tls.net.xml",
    "-r", "grid_5x5/routes.rou.xml",
    "--step-length", "1"
])

PROBS = {
    "straight": 0.6,
    "left": 0.2,
    "right": 0.2
}

last_edge = {}

DEBUG = True  # turn off if too noisy


def pick_weighted(edges):
    if not edges:
        return None

    r = random.random()

    if r < PROBS["straight"]:
        return edges[0]
    elif r < PROBS["straight"] + PROBS["left"]:
        return edges[min(1, len(edges) - 1)]
    else:
        return edges[-1]


while traci.simulation.getMinExpectedNumber() > 0:
    traci.simulationStep()

    for vid in traci.vehicle.getIDList():

        edge = traci.vehicle.getRoadID(vid)

        if edge.startswith(":"):
            continue

        # only decide when entering new edge
        if vid not in last_edge or last_edge[vid] != edge:

            outgoing = traci.edge.getOutgoingIDList(edge)

            if DEBUG:
                print("\n==============================")
                print(f"Vehicle: {vid}")
                print(f"Current edge: {edge}")
                print(f"Outgoing edges: {outgoing}")
                print("==============================\n")

            chosen = pick_weighted(outgoing)

            if chosen:
                try:
                    traci.vehicle.changeTarget(vid, chosen)
                except:
                    pass

        last_edge[vid] = edge

traci.close()