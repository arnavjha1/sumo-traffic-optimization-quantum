import traci
from collections import defaultdict

SUMO_BINARY = "sumo-gui"
SUMO_CONFIG = "sim.sumocfg"
END_TIME = 600

traci.start([SUMO_BINARY, "-c", SUMO_CONFIG])

# -----------------------
# DATA STRUCTURES
# -----------------------
depart_time = {}
route_of = {}
last_waiting_time = {}

travel_times = []
waiting_times = []
throughput = 0

# detect all traffic lights automatically (should be 25)
TLS_ORDER = sorted(traci.trafficlight.getIDList())
NUM_TLS = len(TLS_ORDER)

NUM_LANES = 3  # left / straight / right

queue_lengths = [[[] for _ in range(NUM_LANES)] for _ in range(NUM_TLS)]

# -----------------------
# SIMULATION LOOP
# -----------------------
while traci.simulation.getTime() < END_TIME:
    traci.simulationStep()
    t = traci.simulation.getTime()

    # Vehicles that just departed
    for veh in traci.simulation.getDepartedIDList():
        depart_time[veh] = t
        route_of[veh] = traci.vehicle.getRouteID(veh)
        last_waiting_time[veh] = 0.0

    # Update waiting times
    for veh in traci.vehicle.getIDList():
        last_waiting_time[veh] = traci.vehicle.getAccumulatedWaitingTime(veh)

    # Vehicles that just arrived
    for veh in traci.simulation.getArrivedIDList():
        if veh in depart_time:

            travel_time = t - depart_time[veh]
            waiting_time = last_waiting_time.get(veh, 0.0)

            travel_times.append(travel_time)
            waiting_times.append(waiting_time)

            throughput += 1

            depart_time.pop(veh, None)
            route_of.pop(veh, None)
            last_waiting_time.pop(veh, None)

    # -----------------------
    # QUEUE LENGTH PER TLS
    # -----------------------
    for tls_index, tls in enumerate(TLS_ORDER):

        lanes = traci.trafficlight.getControlledLanes(tls)
        lanes = list(dict.fromkeys(lanes))  # remove duplicates

        for lane_type in range(3):

            if lane_type < len(lanes):
                lane_id = lanes[lane_type]

                queue = 0
                for veh in traci.lane.getLastStepVehicleIDs(lane_id):
                    if traci.vehicle.getSpeed(veh) < 0.1:
                        queue += 1

                queue_lengths[tls_index][lane_type].append(queue)

            else:
                queue_lengths[tls_index][lane_type].append(0)

traci.close()

# -----------------------
# RESULTS
# -----------------------
print("\n===== PERFORMANCE METRICS =====")

# -----------------------
# QUEUE LENGTH
# -----------------------
print("\nAverage Queue Length per Intersection (by lane type):")

LANE_LABELS = ["Left", "Straight", "Right"]

for tls_index, tls in enumerate(TLS_ORDER):
    print(f"\n  {tls}:")
    for lane_type in range(3):

        data = queue_lengths[tls_index][lane_type]

        if len(data) > 0:
            avg = sum(data) / len(data)
            print(f"    {LANE_LABELS[lane_type]}: {avg:.2f} vehicles")
        else:
            print(f"    {LANE_LABELS[lane_type]}: N/A")

# -----------------------
# TRAVEL TIME
# -----------------------
print("\nAverage Travel Time:")

if len(travel_times) > 0:
    avg_travel = sum(travel_times) / len(travel_times)
    print(f"  Overall: {avg_travel:.2f} s")
else:
    print("  Overall: N/A")

# -----------------------
# WAITING TIME
# -----------------------
print("\nAverage Waiting Time:")

if len(waiting_times) > 0:
    avg_wait = sum(waiting_times) / len(waiting_times)
    print(f"  Overall: {avg_wait:.2f} s")
else:
    print("  Overall: N/A")

# -----------------------
# THROUGHPUT
# -----------------------
print("\nThroughput:")

print(f"  Total Vehicles Arrived: {throughput}")