# adaptive_tls_queue_results.py
# SUMO TraCI script for 2x2 grid with queue-based traffic lights and results tracking

import traci
from collections import defaultdict

# ----------------------------
# SIMULATION CONFIG
# ----------------------------
SUMO_BINARY = "sumo-gui"  # change to "sumo" for headless
SUMO_CONFIG = "grid2x2_tls.sumocfg"  # your SUMO config file
SIM_TIME = 3600            # seconds

# ----------------------------
# FIXED OUTPUT ORDER
# ----------------------------
ROUTE_ORDER = ["r0", "r1", "r2", "r3", "r4", "r5"]
TLS_ORDER = ["A0", "A1", "B0", "B1"]

# ----------------------------
# QUEUE PARAMETERS
# ----------------------------
CHECK_INTERVAL = 15        # seconds between queue checks
LEFT_THRESHOLD = 6
STRAIGHT_THRESHOLD = 8

STRAIGHT_PHASE = 0
LEFT_PHASE = 1

# ----------------------------
# DATA STRUCTURES
# ----------------------------
depart_time = {}
route_of = {}
last_waiting_time = {}

travel_times = defaultdict(list)
waiting_times = defaultdict(list)
queue_lengths = defaultdict(list)
throughput = defaultdict(int)

# ----------------------------
# HELPER FUNCTIONS
# ----------------------------
def get_lane_queue(lane_ids):
    """Return number of stopped vehicles in these lanes"""
    q = 0
    for lane in lane_ids:
        for veh_id in traci.lane.getLastStepVehicleIDs(lane):
            if traci.vehicle.getSpeed(veh_id) < 0.1:
                q += 1
    return q

def get_controlled_lanes(tls_id):
    """Return lane IDs controlled by the traffic light"""
    return traci.trafficlight.getControlledLanes(tls_id)

def identify_left_straight_lanes(lanes):
    """Separate left-turn and straight lanes (adjust for your net)"""
    left_lanes = [l for l in lanes if "_16_" in l or "_17_" in l]
    straight_lanes = [l for l in lanes if "_1_" in l or "_5_" in l]
    return left_lanes, straight_lanes

# ----------------------------
# MAIN LOOP
# ----------------------------
def run():
    traci.start([SUMO_BINARY, "-c", SUMO_CONFIG])
    tls_ids = traci.trafficlight.getIDList()
    last_check = defaultdict(lambda: -CHECK_INTERVAL)

    for step in range(SIM_TIME):
        traci.simulationStep()
        t = traci.simulation.getTime()

        # --- Update traffic light phases ---
        for tls in tls_ids:
            if t - last_check[tls] < CHECK_INTERVAL:
                continue
            last_check[tls] = t

            lanes = get_controlled_lanes(tls)
            left_lanes, straight_lanes = identify_left_straight_lanes(lanes)

            left_q = get_lane_queue(left_lanes)
            straight_q = get_lane_queue(straight_lanes)

            current_phase = traci.trafficlight.getPhase(tls)

            if left_q > LEFT_THRESHOLD and current_phase != LEFT_PHASE:
                traci.trafficlight.setPhase(tls, LEFT_PHASE)
            elif straight_q > STRAIGHT_THRESHOLD and current_phase != STRAIGHT_PHASE:
                traci.trafficlight.setPhase(tls, STRAIGHT_PHASE)

            # --- Record average queue lengths ---
            queue_lengths[tls].append(left_q + straight_q)

        # --- Track vehicles for travel time and waiting time ---
        for veh_id in traci.vehicle.getIDList():
            route_id = traci.vehicle.getRouteID(veh_id)
            if veh_id not in depart_time:
                depart_time[veh_id] = t
                route_of[veh_id] = route_id
                last_waiting_time[veh_id] = 0

            # Accumulate waiting time
            speed = traci.vehicle.getSpeed(veh_id)
            if speed < 0.1:
                last_waiting_time[veh_id] += 1  # each step = 1s

        # --- Remove arrived vehicles and update travel/waiting times ---
        arrived = traci.simulation.getArrivedIDList()
        for veh_id in arrived:
            route_id = route_of.get(veh_id, None)
            if route_id:
                travel_times[route_id].append(t - depart_time[veh_id])
                waiting_times[route_id].append(last_waiting_time[veh_id])
                throughput[route_id] += 1

            # Clean up
            depart_time.pop(veh_id, None)
            route_of.pop(veh_id, None)
            last_waiting_time.pop(veh_id, None)

    traci.close()

    # ----------------------------
    # RESULTS (ORDERED)
    # ----------------------------
    print("\n===== PERFORMANCE METRICS =====")

    print("\nAverage Travel Time per Route:")
    for route in ROUTE_ORDER:
        if route in travel_times and travel_times[route]:
            avg = sum(travel_times[route]) / len(travel_times[route])
            print(f"  {route}: {avg:.2f} s (n={len(travel_times[route])})")
        else:
            print(f"  {route}: N/A")

    print("\nAverage Waiting Time per Route:")
    for route in ROUTE_ORDER:
        if route in waiting_times and waiting_times[route]:
            avg = sum(waiting_times[route]) / len(waiting_times[route])
            print(f"  {route}: {avg:.2f} s")
        else:
            print(f"  {route}: N/A")

    print("\nAverage Queue Length per Intersection:")
    for tls in TLS_ORDER:
        if tls in queue_lengths and queue_lengths[tls]:
            avg = sum(queue_lengths[tls]) / len(queue_lengths[tls])
            print(f"  {tls}: {avg:.2f} vehicles")
        else:
            print(f"  {tls}: N/A")

    print("\nThroughput:")
    for route in ROUTE_ORDER:
        print(f"  {route}: {throughput.get(route, 0)}")

# ----------------------------
# ENTRY POINT
# ----------------------------
if __name__ == "__main__":
    run()
