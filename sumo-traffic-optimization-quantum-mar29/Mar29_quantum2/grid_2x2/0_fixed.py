import traci
from collections import defaultdict

SUMO_BINARY = "sumo-gui"
SUMO_CONFIG = "sim2x2_data.sumocfg"
ROUTE_GENERATION_END = 86400
MAX_SIM_TIME = 100000
HOUR_SECONDS = 3600
NUM_HOURS = 24

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
hourly_travel_times = [[] for _ in range(NUM_HOURS)]
hourly_waiting_times = [[] for _ in range(NUM_HOURS)]
hourly_throughput = [0 for _ in range(NUM_HOURS)]

# 3D queue storage:
# queue_lengths[tls_index][lane_type][time]
NUM_TLS = 4
NUM_LANES = 3
queue_lengths = [[[] for _ in range(NUM_LANES)] for _ in range(NUM_TLS)]

# -----------------------
# SIMULATION LOOP
# -----------------------
while (
    traci.simulation.getTime() < MAX_SIM_TIME
    and (traci.simulation.getMinExpectedNumber() > 0 or traci.simulation.getTime() < ROUTE_GENERATION_END)
):
    traci.simulationStep()
    t = traci.simulation.getTime()

    for veh in traci.simulation.getDepartedIDList():
        depart_time[veh] = t
        route_of[veh] = traci.vehicle.getRouteID(veh)
        last_waiting_time[veh] = 0.0

    for veh in traci.vehicle.getIDList():
        last_waiting_time[veh] = traci.vehicle.getAccumulatedWaitingTime(veh)

    for veh in traci.simulation.getArrivedIDList():
        if veh in depart_time:
            route = route_of[veh]
            dep_t = depart_time[veh]

            travel_time = t - dep_t
            waiting_time = last_waiting_time.get(veh, 0.0)

            # Bucket by departure hour, not arrival hour
            hour_index = int(dep_t // HOUR_SECONDS)

            if 0 <= hour_index < NUM_HOURS:
                travel_times[route].append(travel_time)
                waiting_times[route].append(waiting_time)
                throughput[route] += 1

                hourly_travel_times[hour_index].append(travel_time)
                hourly_waiting_times[hour_index].append(waiting_time)
                hourly_throughput[hour_index] += 1

            depart_time.pop(veh, None)
            route_of.pop(veh, None)
            last_waiting_time.pop(veh, None)

    # -----------------------
    # QUEUE LENGTH PER TLS PER LANE
    # -----------------------
    for tls_index, tls in enumerate(TLS_ORDER):

        lanes = traci.trafficlight.getControlledLanes(tls)
        lanes = list(dict.fromkeys(lanes))  # remove duplicates

        # Assumes 3 lanes per incoming direction:
        # lane 0 = left
        # lane 1 = straight
        # lane 2 = right
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

print("\nFIXED")

def compute_avg(values):
    return sum(values) / len(values) if values else None

def format_hour(hour):
    hour_12 = hour % 12
    if hour_12 == 0:
        hour_12 = 12
    suffix = "AM" if hour < 12 else "PM"
    return f"{hour_12}{suffix}"

for hour in range(NUM_HOURS):
    start_label = format_hour(hour)
    end_label = format_hour((hour + 1) % NUM_HOURS)
    avg_travel_time = compute_avg(hourly_travel_times[hour])
    avg_waiting_time = compute_avg(hourly_waiting_times[hour])

    print(f"\nResults for {start_label} - {end_label}:")
    print(f"  Throughput: {hourly_throughput[hour]}")
    print(
        f"  Average Travel Time: {avg_travel_time:.2f} s"
        if avg_travel_time is not None
        else "  Average Travel Time: N/A"
    )
    print(
        f"  Average Waiting Time: {avg_waiting_time:.2f} s"
        if avg_waiting_time is not None
        else "  Average Waiting Time: N/A"
    )
