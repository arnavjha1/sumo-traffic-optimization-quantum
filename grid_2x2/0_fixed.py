import traci
from collections import defaultdict

SUMO_BINARY = "sumo"
SUMO_CONFIG = "sim2x2.sumocfg"
END_TIME = 600

# -----------------------
# FIXED OUTPUT ORDER
# -----------------------
TWO_TURNS = ["r0", "r4", "r6", "r7", "r11", "r13", "r14", "r18", "r20", "r21",
             "r25", "r27", "r28", "r32", "r34", "r35", "r39", "r41", "r42",
             "r46", "r48", "r49", "r53", "r55"]

ONE_TURN = ["r1", "r3", "r5", "r8", "r10", "r12", "r15", "r17", "r19", "r22",
            "r24", "r26", "r29", "r31", "r33", "r36", "r38", "r40", "r43",
            "r45", "r47", "r50", "r52", "r54"]

NO_TURNS = ["r2", "r9", "r16", "r23", "r30", "r37", "r44", "r51"]

TLS_ORDER = ["A0", "A1", "B0", "B1"]

traci.start([SUMO_BINARY, "-c", SUMO_CONFIG])

# -----------------------
# DATA STRUCTURES
# -----------------------
depart_time = {}
route_of = {}
last_waiting_time = {}

travel_times = defaultdict(list)
waiting_times = defaultdict(list)
throughput = defaultdict(int)

NUM_TLS = 4
NUM_LANES = 3

# queue_lengths[tls][lane][time]
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
            route = route_of[veh]
            travel_time = t - depart_time[veh]
            waiting_time = last_waiting_time.get(veh, 0.0)

            travel_times[route].append(travel_time)
            waiting_times[route].append(waiting_time)
            throughput[route] += 1

            # cleanup
            depart_time.pop(veh, None)
            route_of.pop(veh, None)
            last_waiting_time.pop(veh, None)

    # -----------------------
    # QUEUE LENGTH PER TLS PER LANE (kept but simplified)
    # -----------------------
    for tls_index, tls in enumerate(TLS_ORDER):
        lanes = traci.trafficlight.getControlledLanes(tls)
        lanes = list(dict.fromkeys(lanes))

        for lane_type in range(NUM_LANES):
            if lane_type < len(lanes):
                lane_id = lanes[lane_type]

                queue = sum(
                    1 for veh in traci.lane.getLastStepVehicleIDs(lane_id)
                    if traci.vehicle.getSpeed(veh) < 0.1
                )

                queue_lengths[tls_index][lane_type].append(queue)
            else:
                queue_lengths[tls_index][lane_type].append(0)

traci.close()

# -----------------------
# RESULTS
# -----------------------

def compute_avg(route_list, data_dict):
    values = []
    for r in route_list:
        values.extend(data_dict.get(r, []))
    return sum(values) / len(values) if len(values) > 0 else None

def compute_throughput(route_list):
    return sum(throughput.get(r, 0) for r in route_list)

ALL_ROUTES = TWO_TURNS + ONE_TURN + NO_TURNS

# Travel time
avg_all = compute_avg(ALL_ROUTES, travel_times)

# Waiting time
aavg_all = compute_avg(ALL_ROUTES, waiting_times)

# Throughput
thr_all = compute_throughput(ALL_ROUTES)

# -----------------------
# SAFE OUTPUT
# -----------------------
def safe(x):
    return x if x is not None else 0.0

print(f"{safe(avg_all):.2f},{safe(aavg_all):.2f},{thr_all:.2f}")