"""
Canonical 3x3 Seattle Classical Local evaluation.

Seattle framing matches the already-run official 3x3 QAOA experiment:
- 24-hour simulation: 86,400 s
- 900-s measurement warm-up excluded at the start of every hour
- random departure offset: 0-60 s
- completed vehicles attributed to their departure hour
- no post-24h drain period

The working 3x3 Classical Local energy rule, pressure model, neighbor
coupling, and signal-transition wrapper are preserved.
"""

# CLASSICAL LOCAL

import traci
from collections import defaultdict

SUMO_BINARY = "sumo"
SUMO_CONFIG = "grid_3x3/sim3x3_data.sumocfg"

END_TIME = 86400
WARMUP_TIME = 900
RANDOM_DEPART_OFFSET = 60

HOUR_SECONDS = 3600
NUM_HOURS = 24

# -----------------------
# FIXED OUTPUT ORDER
# -----------------------
TLS_ORDER = [
    "A0", "A1", "A2",
    "B0", "B1", "B2",
    "C0", "C1", "C2",
]

TLS_REG = ["A1", "B1", "B2", "C0", "C1", "C2"]
TLS_INVERT = ["A0", "A2", "B0"]

TLS_NEIGHBORS = [
    ["A0", "A1", "B0"],
    ["A1", "A0", "A2", "B1"],
    ["A2", "A1", "B2"],

    ["B0", "A0", "B1", "C0"],
    ["B1", "A1", "B0", "B2", "C1"],
    ["B2", "A2", "B1", "C2"],

    ["C0", "B0", "C1"],
    ["C1", "B1", "C0", "C2"],
    ["C2", "B2", "C1"],
]

tIndex = TLS_ORDER.copy()

CYCLE_LENGTH = 120

# -----------------------
# SUMO COMMAND
# -----------------------
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

for tls in TLS_REG:
    traci.trafficlight.setRedYellowGreenState(tls, "GGgrrrGGgrrr")

for tls in TLS_INVERT:
    traci.trafficlight.setRedYellowGreenState(tls, "rrrGGgrrrGGg")

# -----------------------
# CANONICAL SEATTLE METRICS
# -----------------------
depart_time = {}
depart_hour = {}
last_waiting_time = {}

travel_times_by_hour = defaultdict(list)
waiting_times_by_hour = defaultdict(list)
completed_vehicles_by_hour = defaultdict(int)
measured_departures_by_hour = defaultdict(int)

NUM_TLS = 9
sim_module = [0] * NUM_TLS

NUM_SIDES = 4       # Each TLS has 4 incoming sides
NUM_LANES = 3       # Left=2, Straight=1, Right=0

# Initialize 4D queue_lengths: TLS x Side x Lane x Time
queue_lengths = [[ [ [] for _ in range(NUM_LANES) ] for _ in range(NUM_SIDES) ] for _ in range(NUM_TLS)]
regular_cars = [[ [ [] for _ in range(NUM_LANES) ] for _ in range(NUM_SIDES) ] for _ in range(NUM_TLS)]


# -----------------------
# SIMULATION STEP
# -----------------------
def simStep(num_times=1):
    """
    Advance SUMO and collect canonical Seattle metrics.
    Queue/moving-vehicle collection continues below on every simulation step.
    """
    for _ in range(num_times):
        traci.simulationStep()
        t = traci.simulation.getTime()

        local_time = int(t % HOUR_SECONDS)

        # Measure only vehicles departing after the first 900 s of each hour.
        for veh in traci.simulation.getDepartedIDList():
            if local_time >= WARMUP_TIME:
                hour = int(t // HOUR_SECONDS)

                if 0 <= hour < NUM_HOURS:
                    depart_time[veh] = t
                    depart_hour[veh] = hour
                    last_waiting_time[veh] = 0.0
                    measured_departures_by_hour[hour] += 1

        # Update waiting time for measured active vehicles only.
        for veh in traci.vehicle.getIDList():
            if veh in depart_time:
                last_waiting_time[veh] = (
                    traci.vehicle.getAccumulatedWaitingTime(veh)
                )

        # Attribute completed vehicles to their departure hour.
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

        # QUEUE LENGTH / MOVING VEHICLE COLLECTION
        for tls_index, tls in enumerate(TLS_ORDER):

            lanes = traci.trafficlight.getControlledLanes(tls)
            lanes = list(dict.fromkeys(lanes))

            lanes_per_side = len(lanes) // NUM_SIDES

            for side_index in range(NUM_SIDES):

                for lane_index in range(NUM_LANES):

                    lane_pos = (
                        side_index * lanes_per_side
                        + lane_index
                    )

                    if lane_pos < len(lanes):

                        lane_id = lanes[lane_pos]

                        queue = sum(
                            1
                            for veh in traci.lane.getLastStepVehicleIDs(lane_id)
                            if traci.vehicle.getSpeed(veh) < 0.1
                        )

                        reg = sum(
                            1
                            for veh in traci.lane.getLastStepVehicleIDs(lane_id)
                            if traci.vehicle.getSpeed(veh) >= 0.1
                        )

                        regular_cars[
                            tls_index
                        ][side_index][lane_index].append(reg)

                        queue_lengths[
                            tls_index
                        ][side_index][lane_index].append(queue)

                    else:

                        regular_cars[
                            tls_index
                        ][side_index][lane_index].append(0)

                        queue_lengths[
                            tls_index
                        ][side_index][lane_index].append(0)

    return traci.simulation.getTime()

# =============================
# CLASSICAL LOCAL SPECIFIC CODE
# =============================

PHASE_NS = "GGgrrrGGgrrr"
PHASE_EW = "rrrGGgrrrGGg"

MIN_CHANGE_TIME = 16

HALF_CYCLE = CYCLE_LENGTH // 2
GREEN_END_1 = HALF_CYCLE - 5
YELLOW_END_1 = HALF_CYCLE - 1

GREEN_END_2 = CYCLE_LENGTH - 5
YELLOW_END_2 = CYCLE_LENGTH - 1

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


# ==========================================================
# ENERGY-BASED PHASE OPTIMIZATION
# ==========================================================

LAMBDA_SWITCHING_PENALTY = 20   # tune between 15–30
coupling_bias = 2             # tune between 0-10

x_i = [[] for _ in range(NUM_TLS)]

def optimize_x_i(tls_index, bias_i):

    # First timestep initialization
    if len(x_i[tls_index]) == 0:
        if bias_i >= 0:
            x_i[tls_index].append(1)
        else:
            x_i[tls_index].append(-1)
        return

    current_x = x_i[tls_index][-1]
    delta = bias_i

    # Energy if we keep current phase
    energy_stay = -delta * current_x

    # Energy if we keep current phase: Coupling with neighbors
    if len(x_i[NUM_TLS - 1]) > 0:
        for neighbor_tls in TLS_NEIGHBORS[tls_index][1:]:
            neighbor_index = tIndex.index(neighbor_tls)
            if len(x_i[neighbor_index]) > 0:
                energy_stay -= coupling_bias * (x_i[neighbor_index][-1] * current_x)

    # Energy if we switch phase
    energy_switch = -delta * (-current_x) + LAMBDA_SWITCHING_PENALTY

    # Energy if we switch phase: Coupling with neighbors
    if len(x_i[NUM_TLS - 1]) > 0:
        for neighbor_tls in TLS_NEIGHBORS[tls_index][1:]:
            neighbor_index = tIndex.index(neighbor_tls)
            if len(x_i[neighbor_index]) > 0:
                energy_switch -= coupling_bias * (x_i[neighbor_index][-1] * (-current_x))

    if energy_switch < energy_stay:
        x_i[tls_index].append(-current_x)
    else:
        x_i[tls_index].append(current_x)


# -----------------------
# SIMULATION LOOP
# -----------------------
sim_module = [0] * NUM_TLS

print("\n===== 3x3 CLASSICAL LOCAL SEATTLE EVALUATION =====")
print(f"Simulation duration: {END_TIME} s")
print(f"Warm-up excluded: first {WARMUP_TIME} s of every hour")
print(f"Random departure offset: 0-{RANDOM_DEPART_OFFSET} s")

while traci.simulation.getTime() < END_TIME:
    simStep()

    compute_pressure()
    compute_discharging_pressure()

    for tls in TLS_REG:
        current_state = traci.trafficlight.getRedYellowGreenState(tls)
        t = traci.simulation.getTime()

        if(current_state == "GGgrrrGGgrrr"):
            bias_i = (discharging_pressure[tIndex.index(tls)][0][-1] + discharging_pressure[tIndex.index(tls)][2][-1]) - (pressure[tIndex.index(tls)][1][-1] + pressure[tIndex.index(tls)][3][-1])
        elif(current_state == "rrrGGgrrrGGg"):
            bias_i = (pressure[tIndex.index(tls)][0][-1] + pressure[tIndex.index(tls)][2][-1]) - (discharging_pressure[tIndex.index(tls)][1][-1] + discharging_pressure[tIndex.index(tls)][3][-1])
        else:
            bias_i = (pressure[tIndex.index(tls)][0][-1] + pressure[tIndex.index(tls)][2][-1]) - (pressure[tIndex.index(tls)][1][-1] + pressure[tIndex.index(tls)][3][-1])
        
        optimize_x_i(tIndex.index(tls), bias_i)


        tls_index = TLS_ORDER.index(tls)
        if (sim_module[tls_index] >= 0 and sim_module[tls_index] < GREEN_END_1):
            traci.trafficlight.setRedYellowGreenState(tls, PHASE_NS)
            if (sim_module[tls_index] >= MIN_CHANGE_TIME and x_i[tls_index][-1] == -1):
                sim_module[tls_index] = GREEN_END_1
            else:
                sim_module[tls_index] += 1

        elif (sim_module[tls_index] >= GREEN_END_1 and sim_module[tls_index] < YELLOW_END_1):
            traci.trafficlight.setRedYellowGreenState(tls,"yyyrrryyyrrr")
            sim_module[tls_index] += 1

        elif (sim_module[tls_index] >= YELLOW_END_1 and sim_module[tls_index] < HALF_CYCLE):
            traci.trafficlight.setRedYellowGreenState(tls, "rrrrrrrrrrrr")
            sim_module[tls_index] += 1

        elif (sim_module[tls_index] >= HALF_CYCLE and sim_module[tls_index] < GREEN_END_2):
            traci.trafficlight.setRedYellowGreenState(tls, PHASE_EW)
            if (sim_module[tls_index] >= (MIN_CHANGE_TIME + HALF_CYCLE) and x_i[tls_index][-1] == 1):
                sim_module[tls_index] = GREEN_END_2
            else:
                sim_module[tls_index] += 1

        elif (sim_module[tls_index] >= GREEN_END_2 and sim_module[tls_index] < YELLOW_END_2):
            traci.trafficlight.setRedYellowGreenState(tls, "rrryyyrrryyy")
            sim_module[tls_index] += 1

        elif (sim_module[tls_index] >= YELLOW_END_2 and sim_module[tls_index] < CYCLE_LENGTH):
            traci.trafficlight.setRedYellowGreenState(tls, "rrrrrrrrrrrr")
            sim_module[tls_index] = 0

    for tls in TLS_INVERT:
        current_state = traci.trafficlight.getRedYellowGreenState(tls)
        t = traci.simulation.getTime()

        if(current_state == "GGgrrrGGgrrr"):
            bias_i = (discharging_pressure[tIndex.index(tls)][0][-1] + discharging_pressure[tIndex.index(tls)][2][-1]) - (pressure[tIndex.index(tls)][1][-1] + pressure[tIndex.index(tls)][3][-1])
        elif(current_state == "rrrGGgrrrGGg"):
            bias_i = (pressure[tIndex.index(tls)][0][-1] + pressure[tIndex.index(tls)][2][-1]) - (discharging_pressure[tIndex.index(tls)][1][-1] + discharging_pressure[tIndex.index(tls)][3][-1])
        else:
            bias_i = (pressure[tIndex.index(tls)][0][-1] + pressure[tIndex.index(tls)][2][-1]) - (pressure[tIndex.index(tls)][1][-1] + pressure[tIndex.index(tls)][3][-1])
        
        optimize_x_i(tIndex.index(tls), bias_i)


        tls_index = TLS_ORDER.index(tls)
        if (sim_module[tls_index] >= 0 and sim_module[tls_index] < GREEN_END_1):
            traci.trafficlight.setRedYellowGreenState(tls, PHASE_EW)
            if (sim_module[tls_index] >= MIN_CHANGE_TIME and x_i[tls_index][-1] == 1):
                sim_module[tls_index] = GREEN_END_1
            else:
                sim_module[tls_index] += 1

        elif (sim_module[tls_index] >= GREEN_END_1 and sim_module[tls_index] < YELLOW_END_1):
            traci.trafficlight.setRedYellowGreenState(tls,"rrryyyrrryyy")
            sim_module[tls_index] += 1

        elif (sim_module[tls_index] >= YELLOW_END_1 and sim_module[tls_index] < HALF_CYCLE):
            traci.trafficlight.setRedYellowGreenState(tls, "rrrrrrrrrrrr")
            sim_module[tls_index] += 1

        elif (sim_module[tls_index] >= HALF_CYCLE and sim_module[tls_index] < GREEN_END_2):
            traci.trafficlight.setRedYellowGreenState(tls, PHASE_NS)
            if (sim_module[tls_index] >= (MIN_CHANGE_TIME + HALF_CYCLE) and x_i[tls_index][-1] == -1):
                sim_module[tls_index] = GREEN_END_2
            else:
                sim_module[tls_index] += 1

        elif (sim_module[tls_index] >= GREEN_END_2 and sim_module[tls_index] < YELLOW_END_2):
            traci.trafficlight.setRedYellowGreenState(tls, "yyyrrryyyrrr")
            sim_module[tls_index] += 1

        elif (sim_module[tls_index] >= YELLOW_END_2 and sim_module[tls_index] < CYCLE_LENGTH):
            traci.trafficlight.setRedYellowGreenState(tls, "rrrrrrrrrrrr")
            sim_module[tls_index] = 0


    current_time = int(traci.simulation.getTime())

    if current_time % HOUR_SECONDS == 0:
        print(
            f"t={current_time:5d} s | "
            f"hour={min(current_time // HOUR_SECONDS, 24):02d} | "
            f"measured_departed={sum(measured_departures_by_hour.values())} | "
            f"measured_completed={sum(completed_vehicles_by_hour.values())} | "
            f"active={traci.vehicle.getIDCount()}"
        )

traci.close()

# -----------------------
# CANONICAL SEATTLE RESULTS
# -----------------------

print("\n===== 3x3 CLASSICAL LOCAL SEATTLE PERFORMANCE METRICS =====")
print(f"Simulation duration: {END_TIME} s")
print(f"Warm-up excluded: first {WARMUP_TIME} s of every hour")
print(f"Random departure offset: 0-{RANDOM_DEPART_OFFSET} s")

print("\nHourly Average Travel Time / Waiting Time:")

all_travel_times = []
all_waiting_times = []

for hour in range(NUM_HOURS):
    tt_values = travel_times_by_hour.get(hour, [])
    wt_values = waiting_times_by_hour.get(hour, [])

    measured_departures = measured_departures_by_hour.get(hour, 0)
    completed = completed_vehicles_by_hour.get(hour, 0)
    unfinished = measured_departures - completed

    if tt_values:
        avg_tt = sum(tt_values) / len(tt_values)
        avg_wt = sum(wt_values) / len(wt_values)

        all_travel_times.extend(tt_values)
        all_waiting_times.extend(wt_values)

        measurement_window = (
            f"{WARMUP_TIME}-3600 s "
            f"({(HOUR_SECONDS - WARMUP_TIME) // 60} min)"
        )

        print(
            f"Hour {hour:02d}: "
            f"TT={avg_tt:.2f} s, "
            f"WT={avg_wt:.2f} s, "
            f"n={len(tt_values)}, "
            f"departed={measured_departures}, "
            f"unfinished={unfinished}, "
            f"window={measurement_window}"
        )
    else:
        print(
            f"Hour {hour:02d}: "
            f"TT=N/A, WT=N/A, n=0, "
            f"departed={measured_departures}, "
            f"unfinished={unfinished}"
        )

if all_travel_times:
    overall_tt = sum(all_travel_times) / len(all_travel_times)
    overall_wt = sum(all_waiting_times) / len(all_waiting_times)
    total_completed = len(all_travel_times)
    total_measured_departures = sum(measured_departures_by_hour.values())

    print("\nPost-warm-up Overall:")
    print(f"Average Travel Time: {overall_tt:.2f} s")
    print(f"Average Waiting Time: {overall_wt:.2f} s")
    print(f"Measured completed vehicles: {total_completed}")
    print(f"Measured departures: {total_measured_departures}")
    print(
        f"Measured unfinished at t={END_TIME}: "
        f"{total_measured_departures - total_completed}"
    )
