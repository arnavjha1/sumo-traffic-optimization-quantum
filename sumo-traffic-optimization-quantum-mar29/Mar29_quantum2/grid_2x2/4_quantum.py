# QAOA GLOBAL

import traci
import json
import os
from itertools import product
from collections import defaultdict, Counter
from annealer_quantum import quantum_decision

SUMO_BINARY = "sumo"
SUMO_CONFIG = "sim2x2_data.sumocfg"
END_TIME = 86400

WARMUP_TIME = 900
RANDOM_DEPART_OFFSET = 60

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

sumo_cmd = [
    SUMO_BINARY,
    "-c", SUMO_CONFIG,
    "--random-depart-offset", str(RANDOM_DEPART_OFFSET),
]

traci.start(sumo_cmd)

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
depart_hour = {}
last_waiting_time = {}

travel_times_by_hour = defaultdict(list)
waiting_times_by_hour = defaultdict(list)

completed_vehicles_by_hour = defaultdict(int)

NUM_TLS = 4
NUM_SIDES = 4       # Each TLS has 4 incoming sides
NUM_LANES = 3       # Left=2, Straight=1, Right=0

# Reviewer analysis settings. Defaults preserve the current QAOA behavior.
ENERGY_LAMBDA = 10
QAOA_SHOTS = int(os.environ.get("QAOA_SHOTS", "512"))

# Seattle hourly QAOA calibration settings
CALIBRATION_DURATION = 25

parameter_counts = Counter()
parameter_energy_sum = defaultdict(float)

fixed_params = None
current_calibration_hour = None

hourly_qaoa_parameters = {}

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
            if (t % 3600) >= WARMUP_TIME:
                depart_time[veh] = t
                depart_hour[veh] = int(t // 3600)
                last_waiting_time[veh] = 0.0

        # Update waiting times
        active_measured = set(depart_time.keys())
        for veh in traci.vehicle.getIDList():
            if veh in active_measured:
                last_waiting_time[veh] = traci.vehicle.getAccumulatedWaitingTime(veh)

        # Vehicles that just arrived
        for veh in traci.simulation.getArrivedIDList():

            if veh in depart_time:

                travel_time = t - depart_time[veh]
                waiting_time = last_waiting_time.get(veh, 0.0)

                hour = depart_hour[veh]

                travel_times_by_hour[hour].append(travel_time)
                waiting_times_by_hour[hour].append(waiting_time)
                completed_vehicles_by_hour[hour] += 1

                depart_time.pop(veh, None)
                depart_hour.pop(veh, None)
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

x_i = [
    [-1] if tls in TLS_REG else [1]
    for tls in TLS_ORDER
]

# -----------------------
# ENERGY BENCHMARKING
# -----------------------
energy_selected = []
energy_exact = []
energy_gaps = []
energy_reductions = []
energy_optimum_hits = 0

# Hourly reviewer energy metrics
energy_selected_by_hour = defaultdict(list)
energy_exact_by_hour = defaultdict(list)
energy_gaps_by_hour = defaultdict(list)
energy_reductions_by_hour = defaultdict(list)

energy_optimum_hits_by_hour = defaultdict(int)
energy_decisions_by_hour = defaultdict(int)

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

    current_time = int(traci.simulation.getTime())
    current_hour = int(current_time // 3600)
    local_time = current_time % 3600

    if current_hour != current_calibration_hour:
        current_calibration_hour = current_hour
        parameter_counts.clear()
        parameter_energy_sum.clear()
        print(f"\n===== HOUR {current_hour:02d} WARMUP BEGINS =====")

        print(
            f"\n===== HOUR {current_hour:02d} START ====="
        )
        print(
            f"Warmup: t={current_hour * 3600} "
            f"to {current_hour * 3600 + WARMUP_TIME - 1}"
        )
        print(
            f"Calibration: "
            f"t={current_hour * 3600 + WARMUP_TIME} "
            f"to "
            f"{current_hour * 3600 + WARMUP_TIME + CALIBRATION_DURATION - 1}"
        )

    hour_start = current_hour * 3600

    calibration_start = hour_start + WARMUP_TIME
    calibration_end = calibration_start + CALIBRATION_DURATION

    assert len(bias_list) == 4
    assert len(prev_state) == 4
    assert len(neighbor_indices) == 4

    if local_time < WARMUP_TIME:
        if fixed_params is None:
            (   bitstring,
                best_gamma, best_beta, best_p,
                best_expected_energy
            ) = quantum_decision(
                bias_list,
                prev_state,
                neighbor_indices,
                coupling_strength=2,
                shots=QAOA_SHOTS,
                return_metadata=True
            )

            fixed_params = round(float(best_gamma), 12), round(float(best_beta), 12), int(best_p)

            print("\n===== INITIAL WARMUP QAOA PARAMETERS =====")
            print(f"Gamma: {fixed_params[0]:.6f}")
            print(f"Beta:  {fixed_params[1]:.6f}")
            print(f"p:     {fixed_params[2]}")
            print("==========================================\n")

        else:
            if local_time == 0:
                print(
                    f"Hour {current_hour:02d} warmup using previous fixed params: "
                    f"gamma={fixed_params[0]:.6f}, "
                    f"beta={fixed_params[1]:.6f}, "
                    f"p={fixed_params[2]}"
                )

            bitstring = quantum_decision(
                bias_list,
                prev_state,
                neighbor_indices,
                coupling_strength=2,
                shots=QAOA_SHOTS,
                fixed_params=fixed_params
            )

    elif calibration_start <= current_time < calibration_end:
        if current_time == calibration_start:
            print(
                f"\n===== HOUR {current_hour:02d} "
                f"QAOA CALIBRATION START ====="
            )

        (
            bitstring,
            best_gamma,
            best_beta,
            best_p,
            best_expected_energy
        ) = quantum_decision(
            bias_list,
            prev_state,
            neighbor_indices,
            coupling_strength=2,
            shots=QAOA_SHOTS,
            return_metadata=True,
            debug=True
        )

        param_key = (
            round(float(best_gamma), 12),
            round(float(best_beta), 12),
            int(best_p)
        )

        parameter_counts[param_key] += 1
        parameter_energy_sum[param_key] += best_expected_energy

        if current_time == calibration_end - 1:
            max_wins = max(parameter_counts.values())

            candidates = [
                params
                for params, count in parameter_counts.items()
                if count == max_wins
            ]

            fixed_params = min(
                candidates,
                key=lambda params:
                    parameter_energy_sum[params]
                    / parameter_counts[params]
            )

            hourly_qaoa_parameters[current_hour] = {
                "gamma": fixed_params[0],
                "beta": fixed_params[1],
                "p": fixed_params[2],
                "wins": parameter_counts[fixed_params],
                "calibration_decisions": CALIBRATION_DURATION
            }

            print(
                f"\n===== QAOA CALIBRATION COMPLETE: "
                f"HOUR {current_hour:02d} ====="
            )
            print(f"Fixed gamma: {fixed_params[0]:.6f}")
            print(f"Fixed beta:  {fixed_params[1]:.6f}")
            print(f"Fixed p:     {fixed_params[2]}")
            print(
                f"Wins:        "
                f"{parameter_counts[fixed_params]}"
                f"/{CALIBRATION_DURATION}"
            )
            print(
                "===== FIXED-PARAMETER QAOA BEGINS =====\n"
            )
            
    else:
        if current_time == calibration_end:
            print(
                f"Hour {current_hour:02d} fixed QAOA begins: "
                f"gamma={fixed_params[0]:.6f}, "
                f"beta={fixed_params[1]:.6f}, "
                f"p={fixed_params[2]}"
            )

        bitstring = quantum_decision(
            bias_list,
            prev_state,
            neighbor_indices,
            coupling_strength=2,
            shots=QAOA_SHOTS,
            fixed_params=fixed_params
        )

    assert len(bitstring) == 4

    if local_time >= WARMUP_TIME:

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

        previous_bitstring = "".join(
            str(state) for state in prev_state
        )

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
        energy_reductions.append(
            previous_energy - selected_energy
        )

        if abs(gap) <= 1e-9:
            energy_optimum_hits += 1

        energy_selected_by_hour[current_hour].append(
            selected_energy
        )

        energy_exact_by_hour[current_hour].append(
            exact_min_energy
        )

        energy_gaps_by_hour[current_hour].append(
            gap
        )

        energy_reductions_by_hour[current_hour].append(
            previous_energy - selected_energy
        )

        energy_decisions_by_hour[current_hour] += 1

        if abs(gap) <= 1e-9:
            energy_optimum_hits_by_hour[current_hour] += 1

    # Update x_i with quantum decisions
    for idx, tls in enumerate(TLS_ORDER):
        x_i[idx].append(
            1 if bitstring[idx] == '1' else -1
        )

    # ====================================================

traci.close()

# -----------------------
# RESULTS
# -----------------------

print("\n===== 2x2 QAOA SEATTLE PERFORMANCE METRICS =====")
print(f"Simulation duration: {END_TIME} s")
print(f"Warm-up excluded: first {WARMUP_TIME} s of every hour")
print(f"Random departure offset: 0-{RANDOM_DEPART_OFFSET} s")

print("\nHourly Average Travel Time / Waiting Time:")

all_travel_times = []
all_waiting_times = []

for hour in range(24):

    tt_values = travel_times_by_hour.get(hour, [])
    wt_values = waiting_times_by_hour.get(hour, [])

    if tt_values:

        avg_tt = sum(tt_values) / len(tt_values)
        avg_wt = sum(wt_values) / len(wt_values)

        all_travel_times.extend(tt_values)
        all_waiting_times.extend(wt_values)

        measurement_window = (
            f"{WARMUP_TIME}-3600 s "
            f"({(3600 - WARMUP_TIME) // 60} min)"
        )

        print(
            f"Hour {hour:02d}: "
            f"TT={avg_tt:.2f} s, "
            f"WT={avg_wt:.2f} s, "
            f"n={len(tt_values)}, "
            f"window={measurement_window}"
        )

    else:

        print(
            f"Hour {hour:02d}: "
            f"TT=N/A, WT=N/A, n=0"
        )

if all_travel_times:

    overall_tt = (
        sum(all_travel_times)
        / len(all_travel_times)
    )

    overall_wt = (
        sum(all_waiting_times)
        / len(all_waiting_times)
    )

    print("\nPost-warm-up Overall:")
    print(
        f"Average Travel Time: "
        f"{overall_tt:.2f} s"
    )
    print(
        f"Average Waiting Time: "
        f"{overall_wt:.2f} s"
    )
    print(
        f"Measured completed vehicles: "
        f"{len(all_travel_times)}"
    )

print("\n===== HOURLY QAOA PARAMETERS =====")

for hour in range(24):

    params = hourly_qaoa_parameters.get(hour)

    if params is None:

        print(
            f"Hour {hour:02d}: "
            f"No completed calibration"
        )

    else:

        print(
            f"Hour {hour:02d}: "
            f"gamma={params['gamma']:.6f}, "
            f"beta={params['beta']:.6f}, "
            f"p={params['p']}, "
            f"wins={params['wins']}/"
            f"{params['calibration_decisions']}"
        )


hourly_energy_summary = {}

print("\n===== HOURLY ENERGY BENCHMARK =====")

for hour in range(24):

    selected_values = energy_selected_by_hour.get(
        hour, []
    )

    exact_values = energy_exact_by_hour.get(
        hour, []
    )

    gap_values = energy_gaps_by_hour.get(
        hour, []
    )

    reduction_values = energy_reductions_by_hour.get(
        hour, []
    )

    num_decisions = energy_decisions_by_hour.get(
        hour, 0
    )

    optimal_hits = energy_optimum_hits_by_hour.get(
        hour, 0
    )

    if num_decisions > 0:
        summary = {
            "num_decisions": num_decisions,
            "optimal_hits": optimal_hits,
            "optimum_recovery_rate":
                optimal_hits / num_decisions,

            "average_selected_energy":
                sum(selected_values)
                / len(selected_values),

            "average_exact_min_energy":
                sum(exact_values)
                / len(exact_values),

            "average_optimality_gap":
                sum(gap_values)
                / len(gap_values),

            "maximum_optimality_gap":
                max(gap_values),

            "average_energy_reduction":
                sum(reduction_values)
                / len(reduction_values)
        }

    else:
        summary = {
            "num_decisions": 0,
            "optimal_hits": 0,
            "optimum_recovery_rate": None,
            "average_selected_energy": None,
            "average_exact_min_energy": None,
            "average_optimality_gap": None,
            "maximum_optimality_gap": None,
            "average_energy_reduction": None
        }

    
    hourly_energy_summary[hour] = summary

    if num_decisions > 0:

        print(
            f"Hour {hour:02d}: "
            f"decisions={num_decisions}, "
            f"hits={optimal_hits}, "
            f"recovery="
            f"{summary['optimum_recovery_rate']:.4f}, "
            f"avg_gap="
            f"{summary['average_optimality_gap']:.4f}, "
            f"max_gap="
            f"{summary['maximum_optimality_gap']:.4f}"
        )

    else:

        print(
            f"Hour {hour:02d}: "
            f"No measured energy decisions"
        )

print("HOURLY_QAOA_PARAMS_JSON: " + json.dumps(hourly_qaoa_parameters))
print("HOURLY_ENERGY_JSON: "      + json.dumps(hourly_energy_summary) )

if energy_selected:

    energy_summary = {
        "shots": QAOA_SHOTS,
        "num_decisions": len(energy_selected),
        "optimal_hits": energy_optimum_hits,
        "optimum_recovery_rate":
            energy_optimum_hits / len(energy_selected),

        "average_selected_energy":
            sum(energy_selected) / len(energy_selected),

        "average_exact_min_energy":
            sum(energy_exact) / len(energy_exact),

        "average_optimality_gap":
            sum(energy_gaps) / len(energy_gaps),

        "maximum_optimality_gap":
            max(energy_gaps),

        "average_energy_reduction":
            sum(energy_reductions) / len(energy_reductions)
    }

else:

    energy_summary = {
        "shots": QAOA_SHOTS,
        "num_decisions": 0,
        "optimal_hits": 0,
        "optimum_recovery_rate": None,
        "average_selected_energy": None,
        "average_exact_min_energy": None,
        "average_optimality_gap": None,
        "maximum_optimality_gap": None,
        "average_energy_reduction": None
    }


print(
    "HOURLY_QAOA_PARAMS_JSON: "
    + json.dumps(hourly_qaoa_parameters)
)

print(
    "HOURLY_ENERGY_JSON: "
    + json.dumps(hourly_energy_summary)
)

print(
    "ENERGY_JSON: "
    + json.dumps(energy_summary)
)