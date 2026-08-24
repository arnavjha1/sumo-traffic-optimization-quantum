# QAOA GLOBAL

import traci
import json
import os
from itertools import product
from collections import defaultdict
from annealer_quantum import quantum_decision

SUMO_BINARY = "sumo"
SUMO_CONFIG = "sim2x2_a2.sumocfg"
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

NUM_TLS = 4
NUM_SIDES = 4       # Each TLS has 4 incoming sides
NUM_LANES = 3       # Left=2, Straight=1, Right=0

# Reviewer analysis settings. Defaults preserve the current QAOA behavior.
ENERGY_LAMBDA = 10
QAOA_SHOTS = int(os.environ.get("QAOA_SHOTS", "512"))

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

                travel_times[route].append(travel_time)
                waiting_times[route].append(waiting_time)
                throughput[route] += 1

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
DOWNSTREAM_K = 0.5

pressure = [
    [[] for _ in range(NUM_SIDES)]
    for _ in range(NUM_TLS)
]

discharging_pressure = [
    [[] for _ in range(NUM_SIDES)]
    for _ in range(NUM_TLS)
]


def get_lane_queue(lane_id):
    """
    Number of stopped/queued vehicles on a lane.
    Uses the same < 0.1 m/s threshold as the rest
    of the simulation.
    """

    if lane_id is None or lane_id == "":
        return 0

    return sum(
        1
        for veh in traci.lane.getLastStepVehicleIDs(lane_id)
        if traci.vehicle.getSpeed(veh) < 0.1
    )


def get_downstream_queue_for_side(tls, side_index):
    """
    Returns downstream congestion associated with
    the incoming lanes belonging to one side of an
    intersection.

    Duplicate outgoing lanes are counted only once.
    """

    lanes = traci.trafficlight.getControlledLanes(tls)
    lanes = list(dict.fromkeys(lanes))

    lanes_per_side = len(lanes) // NUM_SIDES

    start = side_index * lanes_per_side
    end = start + lanes_per_side

    incoming_lanes = lanes[start:end]

    downstream_lanes = set()

    for incoming_lane in incoming_lanes:

        # SUMO returns all lane-to-lane connections
        # leaving this incoming lane.
        for link in traci.lane.getLinks(incoming_lane):

            outgoing_lane = link[0]

            if outgoing_lane:
                downstream_lanes.add(outgoing_lane)

    downstream_queue = sum(
        get_lane_queue(lane_id)
        for lane_id in downstream_lanes
    )

    return downstream_queue


def compute_pressure():

    for tls in TLS_ORDER:

        tls_index = tIndex.index(tls)

        for side_index in range(NUM_SIDES):

            left_queue = (
                queue_lengths[tls_index][side_index][2][-1]
            )

            left_reg = (
                regular_cars[tls_index][side_index][2][-1]
            )

            straight_queue = (
                queue_lengths[tls_index][side_index][1][-1]
            )

            straight_reg = (
                regular_cars[tls_index][side_index][1][-1]
            )

            right_queue = (
                queue_lengths[tls_index][side_index][0][-1]
            )

            right_reg = (
                regular_cars[tls_index][side_index][0][-1]
            )

            # -----------------------------------------
            # Original upstream pressure
            # -----------------------------------------

            upstream_pressure = (
                QUEUE_K
                * (
                    LEFT_WEIGHT * left_queue
                    + straight_queue
                    + RIGHT_WEIGHT * right_queue
                )
                +
                REG_K
                * (
                    LEFT_WEIGHT * left_reg
                    + straight_reg
                    + RIGHT_WEIGHT * right_reg
                )
            )

            # -----------------------------------------
            # NEW: downstream congestion
            # -----------------------------------------

            downstream_queue = (
                get_downstream_queue_for_side(
                    tls,
                    side_index
                )
            )

            # -----------------------------------------
            # Net pressure
            # -----------------------------------------

            pressure_value = (
                upstream_pressure
                - DOWNSTREAM_K * downstream_queue
            )

            pressure[tls_index][side_index].append(
                pressure_value
            )


def compute_discharging_pressure():

    for tls in TLS_ORDER:

        tls_index = tIndex.index(tls)

        for side_index in range(NUM_SIDES):

            left_queue = (
                queue_lengths[tls_index][side_index][2][-1]
            )

            left_reg = (
                regular_cars[tls_index][side_index][2][-1]
            )

            straight_queue = (
                queue_lengths[tls_index][side_index][1][-1]
            )

            straight_reg = (
                regular_cars[tls_index][side_index][1][-1]
            )

            right_queue = (
                queue_lengths[tls_index][side_index][0][-1]
            )

            right_reg = (
                regular_cars[tls_index][side_index][0][-1]
            )

            # -----------------------------------------
            # Original discharging pressure
            # -----------------------------------------

            upstream_pressure = (
                DISCHARGE_QUEUE_K
                * (
                    LEFT_WEIGHT * left_queue
                    + straight_queue
                    + RIGHT_WEIGHT * right_queue
                )
                +
                REG_K
                * (
                    LEFT_WEIGHT * left_reg
                    + straight_reg
                    + RIGHT_WEIGHT * right_reg
                )
            )

            # -----------------------------------------
            # NEW: downstream congestion
            # -----------------------------------------

            downstream_queue = (
                get_downstream_queue_for_side(
                    tls,
                    side_index
                )
            )

            # -----------------------------------------
            # Net discharging pressure
            # -----------------------------------------

            pressure_value = (
                upstream_pressure
                - DOWNSTREAM_K * downstream_queue
            )

            discharging_pressure[
                tls_index
            ][side_index].append(
                pressure_value
            )

x_i = [[] for _ in range(NUM_TLS)]

# -----------------------
# ENERGY BENCHMARKING
# -----------------------
energy_selected = []
energy_exact = []
energy_gaps = []
energy_reductions = []
energy_optimum_hits = 0

def calculate_ising_energy(bitstring, biases, prev_state, neighbors, coupling_strength=2):
    # This exactly mirrors the Ising energy used in annealer_quantum.py.
    spins = [1 if bit == "1" else -1 for bit in bitstring]
    prev_spins = [2 * state - 1 for state in prev_state]

    energy = 0.0

    for i in range(NUM_TLS):
        energy += -biases[i] * spins[i]
        energy += -ENERGY_LAMBDA * prev_spins[i] * spins[i]

        for j in neighbors[i]:
            if i < j:
                energy += -coupling_strength * spins[i] * spins[j]

    return energy

def exact_global_minimum(biases, prev_state, neighbors, coupling_strength=2):
    best_energy = float("inf")
    best_states = []

    for state_tuple in product("01", repeat=NUM_TLS):
        state = "".join(state_tuple)
        energy = calculate_ising_energy(
            state,
            biases,
            prev_state,
            neighbors,
            coupling_strength
        )

        if energy < best_energy - 1e-12:
            best_energy = energy
            best_states = [state]
        elif abs(energy - best_energy) <= 1e-12:
            best_states.append(state)

    return best_energy, best_states

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


    # ====================================================
    # QUANTUM ANNEALING OPTIMIZATION
    # ====================================================

    # Convert downstream-aware biases to a flat list (length 4)
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
        coupling_strength=2,
        shots=QAOA_SHOTS
    )

    # Benchmark the selected QAOA state against all 16 possible global states.
    selected_energy = calculate_ising_energy(
        bitstring,
        bias_list,
        prev_state,
        neighbor_indices,
        coupling_strength=2
    )
    exact_min_energy, exact_states = exact_global_minimum(
        bias_list,
        prev_state,
        neighbor_indices,
        coupling_strength=2
    )
    previous_bitstring = "".join(str(state) for state in prev_state)
    previous_energy = calculate_ising_energy(
        previous_bitstring,
        bias_list,
        prev_state,
        neighbor_indices,
        coupling_strength=2
    )

    gap = selected_energy - exact_min_energy
    energy_selected.append(selected_energy)
    energy_exact.append(exact_min_energy)
    energy_gaps.append(gap)
    energy_reductions.append(previous_energy - selected_energy)
    if abs(gap) <= 1e-9:
        energy_optimum_hits += 1

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

def compute_avg(route_list, data_dict):
    values = []
    for r in route_list:
        values.extend(data_dict.get(r, []))
    return sum(values) / len(values) if len(values) > 0 else None

def compute_throughput(route_list):
    return sum(throughput.get(r, 0) for r in route_list)

ALL_ROUTES = TWO_TURNS + ONE_TURN + NO_TURNS

# Queue lengths
print("\nAverage Queue Length per TLS per Side/Lane:")
LANE_LABELS = ["Right", "Straight", "Left"]

for tls_index, tls in enumerate(TLS_ORDER):
    print(f"\n  {tls}:")
    for side_index in range(NUM_SIDES):
        print(f"    Side {side_index}: ", end="")
        for lane_index in range(NUM_LANES):
            data = queue_lengths[tls_index][side_index][lane_index]
            avg = sum(data) / len(data) if data else 0
            print(f"{LANE_LABELS[lane_index]}={avg:.1f} ", end="")
        print()

# Travel time
print("\nQUANTUM")
print("\nAverage Travel Time:")
avg_two = compute_avg(TWO_TURNS, travel_times)
avg_one = compute_avg(ONE_TURN, travel_times)
avg_none = compute_avg(NO_TURNS, travel_times)
avg_all = compute_avg(ALL_ROUTES, travel_times)

print(f"  Two Turns: {avg_two:.2f} s" if avg_two else "  Two Turns: N/A")
print(f"  One Turn:  {avg_one:.2f} s" if avg_one else "  One Turn: N/A")
print(f"  No Turns:  {avg_none:.2f} s" if avg_none else "  No Turns: N/A")
print(f"  Overall:   {avg_all:.2f} s" if avg_all else "  Overall: N/A")

# Waiting time
print("\nAverage Waiting Time:")
avg_two = compute_avg(TWO_TURNS, waiting_times)
avg_one = compute_avg(ONE_TURN, waiting_times)
avg_none = compute_avg(NO_TURNS, waiting_times)
avg_all = compute_avg(ALL_ROUTES, waiting_times)

print(f"  Two Turns: {avg_two:.2f} s" if avg_two else "  Two Turns: N/A")
print(f"  One Turn:  {avg_one:.2f} s" if avg_one else "  One Turn: N/A")
print(f"  No Turns:  {avg_none:.2f} s" if avg_none else "  No Turns: N/A")
print(f"  Overall:   {avg_all:.2f} s" if avg_all else "  Overall: N/A")

# Throughput
print("\nThroughput:")
thr_two = compute_throughput(TWO_TURNS)
thr_one = compute_throughput(ONE_TURN)
thr_none = compute_throughput(NO_TURNS)
thr_all = compute_throughput(ALL_ROUTES)

print(f"  Two Turns: {thr_two}")
print(f"  One Turn:  {thr_one}")
print(f"  No Turns:  {thr_none}")
print(f"  Overall:   {thr_all}")

# -----------------------
# ENERGY BENCHMARK RESULTS
# -----------------------
if energy_selected:
    energy_summary = {
        "shots": QAOA_SHOTS,
        "num_decisions": len(energy_selected),
        "optimal_hits": energy_optimum_hits,
        "optimum_recovery_rate": energy_optimum_hits / len(energy_selected),
        "average_selected_energy": sum(energy_selected) / len(energy_selected),
        "average_exact_min_energy": sum(energy_exact) / len(energy_exact),
        "average_optimality_gap": sum(energy_gaps) / len(energy_gaps),
        "maximum_optimality_gap": max(energy_gaps),
        "average_energy_reduction": sum(energy_reductions) / len(energy_reductions)
    }
else:
    energy_summary = {
        "shots": QAOA_SHOTS,
        "num_decisions": 0,
        "optimal_hits": 0,
        "optimum_recovery_rate": 0.0,
        "average_selected_energy": None,
        "average_exact_min_energy": None,
        "average_optimality_gap": None,
        "maximum_optimality_gap": None,
        "average_energy_reduction": None
    }

print("\n===== ENERGY BENCHMARK =====")
print(f"QAOA Shots: {energy_summary['shots']}")
print(f"Energy Decisions: {energy_summary['num_decisions']}")
print(f"Optimal Hits: {energy_summary['optimal_hits']}")
print(f"Optimum Recovery Rate: {energy_summary['optimum_recovery_rate']:.6f}")
if energy_summary["average_selected_energy"] is not None:
    print(f"Average Selected Energy: {energy_summary['average_selected_energy']:.6f}")
    print(f"Average Exact Minimum Energy: {energy_summary['average_exact_min_energy']:.6f}")
    print(f"Average Optimality Gap: {energy_summary['average_optimality_gap']:.6f}")
    print(f"Maximum Optimality Gap: {energy_summary['maximum_optimality_gap']:.6f}")
    print(f"Average Energy Reduction: {energy_summary['average_energy_reduction']:.6f}")
print("ENERGY_JSON: " + json.dumps(energy_summary))