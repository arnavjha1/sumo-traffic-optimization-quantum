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

        # only decide once per edge
        edge = traci.vehicle.getRoadID(vid)

        if vid not in last_edge or last_edge[vid] != edge:

            links = traci.lane.getLinks(lane_id)

            straight = []
            left = []
            right = []

            for link in links:
                direction = link[6]
                next_lane = link[0]

                if direction == "s":
                    straight.append(next_lane)
                elif direction == "l":
                    left.append(next_lane)
                elif direction == "r":
                    right.append(next_lane)

            r = random.random()

            if r < PROBS["straight"] and straight:
                chosen_lane = random.choice(straight)
            elif r < PROBS["straight"] + PROBS["left"] and left:
                chosen_lane = random.choice(left)
            elif right:
                chosen_lane = random.choice(right)
            else:
                continue

            # THIS is the key fix
            traci.vehicle.setLaneChangeMode(vid, 0b001000000000)

            try:
                traci.vehicle.moveTo(vid, chosen_lane, 0)
            except:
                pass

        last_edge[vid] = edge

traci.close()