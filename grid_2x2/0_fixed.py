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

# 3D queue storage:
# queue_lengths[tls_index][lane_type][time]
NUM_TLS = 4
NUM_SIDES = 4
NUM_LANES = 3
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

#print("\n===== PERFORMANCE METRICS =====")

def compute_avg(route_list, data_dict):
    values = []
    for r in route_list:
        values.extend(data_dict.get(r, []))
    return sum(values) / len(values) if len(values) > 0 else None

def compute_throughput(route_list):
    return sum(throughput.get(r, 0) for r in route_list)

ALL_ROUTES = TWO_TURNS + ONE_TURN + NO_TURNS

# Queue lengths

#print("\nAverage Queue Length per TLS per Side/Lane:")
LANE_LABELS = ["Right", "Straight", "Left"]

for tls_index, tls in enumerate(TLS_ORDER):
    #print(f"\n  {tls}:")
    for side_index in range(NUM_SIDES):
        #print(f"    Side {side_index}: ", end="")
        for lane_index in range(NUM_LANES):
            data = queue_lengths[tls_index][side_index][lane_index]
            avg = sum(data) / len(data) if data else 0
            #print(f"{LANE_LABELS[lane_index]}={avg:.1f} ", end="")
        #print()

# Travel time
#print("\nCLASSICAL")
#print("\nAverage Travel Time:")
avg_two = compute_avg(TWO_TURNS, travel_times)
avg_one = compute_avg(ONE_TURN, travel_times)
avg_none = compute_avg(NO_TURNS, travel_times)
avg_all = compute_avg(ALL_ROUTES, travel_times)

#print(f"  Two Turns: {avg_two:.2f} s" if avg_two else "  Two Turns: N/A")
#print(f"  One Turn:  {avg_one:.2f} s" if avg_one else "  One Turn: N/A")
#print(f"  No Turns:  {avg_none:.2f} s" if avg_none else "  No Turns: N/A")
#print(f"  Overall:   {avg_all:.2f} s" if avg_all else "  Overall: N/A")

# Waiting time
#print("\nAverage Waiting Time:")
aavg_two = compute_avg(TWO_TURNS, waiting_times)
aavg_one = compute_avg(ONE_TURN, waiting_times)
aavg_none = compute_avg(NO_TURNS, waiting_times)
aavg_all = compute_avg(ALL_ROUTES, waiting_times)

#print(f"  Two Turns: {avg_two:.2f} s" if avg_two else "  Two Turns: N/A")
#print(f"  One Turn:  {avg_one:.2f} s" if avg_one else "  One Turn: N/A")
#print(f"  No Turns:  {avg_none:.2f} s" if avg_none else "  No Turns: N/A")
#print(f"  Overall:   {avg_all:.2f} s" if avg_all else "  Overall: N/A")

# Throughput
#print("\nThroughput:")
thr_two = compute_throughput(TWO_TURNS)
thr_one = compute_throughput(ONE_TURN)
thr_none = compute_throughput(NO_TURNS)
thr_all = compute_throughput(ALL_ROUTES)

#print(f"  Two Turns: {thr_two}")
#print(f"  One Turn:  {thr_one}")
#print(f"  No Turns:  {thr_none}")
#print(f"  Overall:   {thr_all}")
print(f"{avg_all:.2f},{aavg_all:.2f},{thr_all}")