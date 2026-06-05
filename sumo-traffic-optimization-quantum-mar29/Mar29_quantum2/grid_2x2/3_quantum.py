import traci
from collections import defaultdict
from annealer_quantum import quantum_decision

SUMO_BINARY = "sumo"
SUMO_CONFIG = "sim2x2_data.sumocfg"
END_TIME = 86400
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
TLS_REG = ["A0", "A1", "B0"]
TLS_INVERT = ["B1"]

TLS_NEIGHBORS = [
    ["A0", "B0", "A1"],  # A0 neighbors
    ["A1", "B1", "A0"],  # A1 neighbors
    ["B0", "A0", "B1"],  # B0 neighbors
    ["B1", "A1", "B0"]   # B1 neighbors
]

traci.start([SUMO_BINARY, "-c", SUMO_CONFIG])

# -----------------------
# FORCE MANUAL TLS CONTROL
# -----------------------
for tls in TLS_ORDER:
    traci.trafficlight.setProgram(tls, "0")
    traci.trafficlight.setPhaseDuration(tls, 999999)

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

NUM_TLS = 4
NUM_SIDES = 4       # Each TLS has 4 incoming sides
NUM_LANES = 3       # Left=2, Straight=1, Right=0

# Initialize 4D queue_lengths: TLS x Side x Lane x Time
queue_lengths = [[ [ [] for _ in range(NUM_LANES) ] for _ in range(NUM_SIDES) ] for _ in range(NUM_TLS)]
regular_cars = [[ [ [] for _ in range(NUM_LANES) ] for _ in range(NUM_SIDES) ] for _ in range(NUM_TLS)]
tIndex = []
bias_i_tls = [[] for _ in range(NUM_TLS)]  # Store bias_i values for each TLS over time

for tls in TLS_REG:
    traci.trafficlight.setRedYellowGreenState(tls, "GGgrrrGGgrrr")
    tIndex.append(tls)
    
for tls in TLS_INVERT:
    traci.trafficlight.setRedYellowGreenState(tls, "rrrGGgrrrGGg")
    tIndex.append(tls)

def simStep(num_times = 1):
    for _ in range(num_times):
        traci.simulationStep()
        t = traci.simulation.getTime()

        # ====================================================
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
                hour_index = min(int(t // HOUR_SECONDS), NUM_HOURS - 1)

                travel_times[route].append(travel_time)
                waiting_times[route].append(waiting_time)
                throughput[route] += 1
                hourly_travel_times[hour_index].append(travel_time)
                hourly_waiting_times[hour_index].append(waiting_time)
                hourly_throughput[hour_index] += 1

                depart_time.pop(veh, None)
                route_of.pop(veh, None)
                last_waiting_time.pop(veh, None)

        # ====================================================
        # QUEUE LENGTH CALCULATION (4D ARRAY)
        for tls_index, tls in enumerate(TLS_ORDER):
            lanes = traci.trafficlight.getControlledLanes(tls)
            lanes = list(dict.fromkeys(lanes))  # remove duplicates

            # Each TLS has 4 sides; split lanes evenly per side
            lanes_per_side = len(lanes) // NUM_SIDES
            for side_index in range(NUM_SIDES):
                for lane_index in range(NUM_LANES):
                    lane_pos = side_index * lanes_per_side + lane_index
                    if lane_pos < len(lanes):
                        lane_id = lanes[lane_pos]
                        queue = sum(1 for veh in traci.lane.getLastStepVehicleIDs(lane_id)
                                    if traci.vehicle.getSpeed(veh) < 0.1)
                        reg   = sum(1 for veh in traci.lane.getLastStepVehicleIDs(lane_id)
                                    if traci.vehicle.getSpeed(veh) >= 0.1)
                        regular_cars[tls_index][side_index][lane_index].append(reg)
                        queue_lengths[tls_index][side_index][lane_index].append(queue)
                    else:
                        regular_cars[tls_index][side_index][lane_index].append(0)
                        queue_lengths[tls_index][side_index][lane_index].append(0)

QUEUE_K = 2
DISCHARGE_QUEUE_K = 1
REG_K = 1
LEFT_WEIGHT = 1.00
RIGHT_WEIGHT = 0.47
pressure = [[ [] for _ in range(NUM_SIDES) ] for _ in range(NUM_TLS)]
discharging_pressure = [[ [] for _ in range(NUM_SIDES) ] for _ in range(NUM_TLS)]

def compute_pressure():
    for tls in TLS_ORDER:
        tls_index = tIndex.index(tls)
        for side_index in range(NUM_SIDES):
            left_queue     = queue_lengths[tls_index][side_index][2][-1]
            left_reg       =  regular_cars[tls_index][side_index][2][-1]
            straight_queue = queue_lengths[tls_index][side_index][1][-1]
            straight_reg   =  regular_cars[tls_index][side_index][1][-1]
            right_queue    = queue_lengths[tls_index][side_index][0][-1]
            right_reg      =  regular_cars[tls_index][side_index][0][-1]

            pressure_value = QUEUE_K * (LEFT_WEIGHT * left_queue + straight_queue + RIGHT_WEIGHT * right_queue) + REG_K * (LEFT_WEIGHT * left_reg + straight_reg + RIGHT_WEIGHT * right_reg)
            pressure[tls_index][side_index].append(pressure_value)

def compute_discharging_pressure():
    for tls in TLS_ORDER:
        tls_index = tIndex.index(tls)
        for side_index in range(NUM_SIDES):
            left_queue     = queue_lengths[tls_index][side_index][2][-1]
            left_reg       =  regular_cars[tls_index][side_index][2][-1]
            straight_queue = queue_lengths[tls_index][side_index][1][-1]
            straight_reg   =  regular_cars[tls_index][side_index][1][-1]
            right_queue    = queue_lengths[tls_index][side_index][0][-1]
            right_reg      =  regular_cars[tls_index][side_index][0][-1]

            pressure_value = DISCHARGE_QUEUE_K * (LEFT_WEIGHT * left_queue + straight_queue + RIGHT_WEIGHT * right_queue) + REG_K * (LEFT_WEIGHT * left_reg + straight_reg + RIGHT_WEIGHT * right_reg)
            discharging_pressure[tls_index][side_index].append(pressure_value)


x_i = [[] for _ in range(NUM_TLS)]

# -----------------------
# SIMULATION LOOP
# -----------------------
sim_module = [0] * len(tIndex)  # Track which module each TLS is in
MIN_CHANGE_TIME = 12  # Minimum time to wait before allowing another change

while traci.simulation.getTime() < END_TIME:

    simStep()
    compute_pressure()
    compute_discharging_pressure()


    # ====================================================
    # QUEUE LENGTH ALGORITHM
    for tls in TLS_REG:
        current_state = traci.trafficlight.getRedYellowGreenState(tls)
        t = traci.simulation.getTime()

        if(current_state == "GGgrrrGGgrrr"):
            bias_i = (discharging_pressure[tIndex.index(tls)][0][-1] + discharging_pressure[tIndex.index(tls)][2][-1]) - (pressure[tIndex.index(tls)][1][-1] + pressure[tIndex.index(tls)][3][-1])
        elif(current_state == "rrrGGgrrrGGg"):
            bias_i = (pressure[tIndex.index(tls)][0][-1] + pressure[tIndex.index(tls)][2][-1]) - (discharging_pressure[tIndex.index(tls)][1][-1] + discharging_pressure[tIndex.index(tls)][3][-1])
        else:
            bias_i = (pressure[tIndex.index(tls)][0][-1] + pressure[tIndex.index(tls)][2][-1]) - (pressure[tIndex.index(tls)][1][-1] + pressure[tIndex.index(tls)][3][-1])
        
        bias_i_tls[tIndex.index(tls)].append(bias_i)

        if sim_module[tIndex.index(tls)] >= 0 and sim_module[tIndex.index(tls)] < 55:
            traci.trafficlight.setRedYellowGreenState(tls, "GGgrrrGGgrrr")
            if(sim_module[tIndex.index(tls)] >= MIN_CHANGE_TIME and x_i[tIndex.index(tls)][-1] == -1):
                sim_module[tIndex.index(tls)] = 55
            else:
                sim_module[tIndex.index(tls)] += 1

        elif sim_module[tIndex.index(tls)] >= 55 and sim_module[tIndex.index(tls)] < 59:
            traci.trafficlight.setRedYellowGreenState(tls, "yyyrrryyyrrr")
            sim_module[tIndex.index(tls)] += 1

        elif sim_module[tIndex.index(tls)] >= 59 and sim_module[tIndex.index(tls)] < 60:
            traci.trafficlight.setRedYellowGreenState(tls, "rrrrrrrrrrrr")
            sim_module[tIndex.index(tls)] += 1

        elif sim_module[tIndex.index(tls)] >= 60 and sim_module[tIndex.index(tls)] < 115:
            traci.trafficlight.setRedYellowGreenState(tls, "rrrGGgrrrGGg")
            if(sim_module[tIndex.index(tls)] >= (MIN_CHANGE_TIME + 60) and x_i[tIndex.index(tls)][-1] == 1):
                sim_module[tIndex.index(tls)] = 115
            else:
                sim_module[tIndex.index(tls)] += 1
                
        elif sim_module[tIndex.index(tls)] >= 115 and sim_module[tIndex.index(tls)] < 119:
            traci.trafficlight.setRedYellowGreenState(tls, "rrryyyrrryyy")
            sim_module[tIndex.index(tls)] += 1

        elif sim_module[tIndex.index(tls)] >= 119 and sim_module[tIndex.index(tls)] < 120:
            traci.trafficlight.setRedYellowGreenState(tls, "rrrrrrrrrrrr")
            sim_module[tIndex.index(tls)] = 0

    for tls in TLS_INVERT:
        current_state = traci.trafficlight.getRedYellowGreenState(tls)
        t = traci.simulation.getTime()

        if(current_state == "GGgrrrGGgrrr"):
            bias_i = (discharging_pressure[tIndex.index(tls)][0][-1] + discharging_pressure[tIndex.index(tls)][2][-1]) - (pressure[tIndex.index(tls)][1][-1] + pressure[tIndex.index(tls)][3][-1])
        elif(current_state == "rrrGGgrrrGGg"):
            bias_i = (pressure[tIndex.index(tls)][0][-1] + pressure[tIndex.index(tls)][2][-1]) - (discharging_pressure[tIndex.index(tls)][1][-1] + discharging_pressure[tIndex.index(tls)][3][-1])
        else:
            bias_i = (pressure[tIndex.index(tls)][0][-1] + pressure[tIndex.index(tls)][2][-1]) - (pressure[tIndex.index(tls)][1][-1] + pressure[tIndex.index(tls)][3][-1])
        
        bias_i_tls[tIndex.index(tls)].append(bias_i)

        
        if sim_module[tIndex.index(tls)] >= 0 and sim_module[tIndex.index(tls)] < 55:
            traci.trafficlight.setRedYellowGreenState(tls, "rrrGGgrrrGGg")
            if(sim_module[tIndex.index(tls)] >= MIN_CHANGE_TIME and x_i[tIndex.index(tls)][-1] == 1):
                sim_module[tIndex.index(tls)] = 55
            else:
                sim_module[tIndex.index(tls)] += 1
                
        elif sim_module[tIndex.index(tls)] >= 55 and sim_module[tIndex.index(tls)] < 59:
            traci.trafficlight.setRedYellowGreenState(tls, "rrryyyrrryyy")
            sim_module[tIndex.index(tls)] += 1

        elif sim_module[tIndex.index(tls)] >= 59 and sim_module[tIndex.index(tls)] < 60:
            traci.trafficlight.setRedYellowGreenState(tls, "rrrrrrrrrrrr")
            sim_module[tIndex.index(tls)] += 1

        elif sim_module[tIndex.index(tls)] >= 60 and sim_module[tIndex.index(tls)] < 115:
            traci.trafficlight.setRedYellowGreenState(tls, "GGgrrrGGgrrr")
            if(sim_module[tIndex.index(tls)] >= (MIN_CHANGE_TIME + 60) and x_i[tIndex.index(tls)][-1] == -1):
                sim_module[tIndex.index(tls)] = 115
            else:
                sim_module[tIndex.index(tls)] += 1

        elif sim_module[tIndex.index(tls)] >= 115 and sim_module[tIndex.index(tls)] < 119:
            traci.trafficlight.setRedYellowGreenState(tls, "yyyrrryyyrrr")
            sim_module[tIndex.index(tls)] += 1

        elif sim_module[tIndex.index(tls)] >= 119 and sim_module[tIndex.index(tls)] < 120:
            traci.trafficlight.setRedYellowGreenState(tls, "rrrrrrrrrrrr")
            sim_module[tIndex.index(tls)] = 0
    
    # ====================================================
    # QUANTUM ANNEALING OPTIMIZATION
    # ====================================================

    # Convert biases to a flat list (length 4)
    bias_list = [bias_i_tls[tIndex.index(tls)][-1] for tls in TLS_ORDER]

    # Previous traffic light states
    # 0 = NS green
    # 1 = EW green

    prev_state = []

    for i in range(NUM_TLS):

        # First timestep fallback
        if len(x_i[i]) == 0:

            # Use initial configuration
            if TLS_ORDER[i] in TLS_REG:
                prev_state.append(0)
            else:
                prev_state.append(1)

        else:

            # Convert {-1,1} -> {0,1}
            prev_state.append(
                1 if x_i[i][-1] == 1 else 0
            )
    
    neighbor_indices = []

    for i in range(NUM_TLS):

        curr_neighbors = []

        for neighbor_tls in TLS_NEIGHBORS[i][1:]:

            curr_neighbors.append(
                tIndex.index(neighbor_tls)
            )

        neighbor_indices.append(curr_neighbors)

    bitstring = quantum_decision(
        bias_list,
        prev_state,
        neighbor_indices,
        coupling_strength=2
    )

    print(traci.simulation.getTime())

    # Update x_i with quantum decisions
    for idx, tls in enumerate(TLS_ORDER):
        x_i[idx].append(1 if bitstring[idx] == '1' else -1)
    # ====================================================

traci.close()

# -----------------------
# RESULTS
# -----------------------
print("\n===== PERFORMANCE METRICS =====")

print("\nQUANTUM")

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
