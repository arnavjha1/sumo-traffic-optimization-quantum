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

SUMO_BINARY = "sumo"  # or "sumo"

sumo_cmd = [
    SUMO_BINARY,
    "-n", "grid5x5_tls.net.xml",
    "-r", "routes.rou.xml"
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


# ---- main loop ----
while traci.simulation.getMinExpectedNumber() > 0:
    traci.simulationStep()

    for vid in traci.vehicle.getIDList():

        edge = traci.vehicle.getRoadID(vid)

        # only act at intersections (edges ending in nodes like A0, B1 etc)
        possible_edges = traci.vehicle.getNextStops(vid)

        # better: use junction logic
        current_edge = traci.vehicle.getRoadID(vid)

        # if vehicle is at a junction decision point
        if ":" in current_edge:  # SUMO junction edges often contain ':'
            continue

        # get outgoing edges from current lane
        allowed = traci.vehicle.getAllowedLinks(vid)

        # fallback: use network structure instead
        next_edges = traci.edge.getOutgoing(current_edge)

        if not next_edges:
            continue

        choice = choose_direction()

        # pick edges
        if choice == "STRAIGHT":
            target = next_edges[0]
        elif choice == "LEFT":
            target = next_edges[min(1, len(next_edges)-1)]
        else:
            target = next_edges[-1]

        traci.vehicle.setRoute(vid, [current_edge, target])


traci.close()