"""
Canonical 3x3 Seattle evaluation shell.

Mirrors the already-run official 3x3 QAOA Seattle framing:
- 24-hour simulation: 86,400 s
- 900-s measurement warm-up excluded at the start of every hour
- random departure offset: 0-60 s
- completed vehicles attributed to departure hour
- no post-24h drain period
- same 3x3 TLS ordering / REG-INVERT orientation
"""

import traci
from collections import defaultdict
from agent import MPLightAgent

SUMO_BINARY = "sumo-gui"
SUMO_CONFIG = "grid_3x3/sim3x3_data.sumocfg"

END_TIME = 86400
WARMUP_TIME = 900
RANDOM_DEPART_OFFSET = 60

HOUR_SECONDS = 3600
NUM_HOURS = 24

TLS_ORDER = [
    "A0", "A1", "A2",
    "B0", "B1", "B2",
    "C0", "C1", "C2",
]

TLS_REG = ["A1", "B1", "B2", "C0", "C1", "C2"]
TLS_INVERT = ["A0", "A2", "B0"]

NUM_TLS = len(TLS_ORDER)
NUM_SIDES = 4
NUM_LANES = 3

PHASE_NS = "GGgrrrGGgrrr"
PHASE_EW = "rrrGGgrrrGGg"
YELLOW_NS_TO_EW = "yyyrrryyyrrr"
YELLOW_EW_TO_NS = "rrryyyrrryyy"
ALL_RED = "rrrrrrrrrrrr"

sumo_cmd = [
    SUMO_BINARY,
    "-c", SUMO_CONFIG,
    "--random-depart-offset", str(RANDOM_DEPART_OFFSET),
]

traci.start(sumo_cmd)

for tls in TLS_ORDER:
    traci.trafficlight.setProgram(tls, "0")
    traci.trafficlight.setPhaseDuration(tls, 999999)

for tls in TLS_REG:
    traci.trafficlight.setRedYellowGreenState(tls, PHASE_NS)

for tls in TLS_INVERT:
    traci.trafficlight.setRedYellowGreenState(tls, PHASE_EW)

# -----------------------
# LOAD FROZEN MPLIGHT MODEL
# -----------------------

MODEL_PATH = "MPLight_model_v1.pt"
DECISION_INTERVAL = 10

agent = MPLightAgent()
agent.load(MODEL_PATH)
agent.set_evaluation_mode()

last_green_phase = {
    tls: (0 if tls in TLS_REG else 1)
    for tls in TLS_ORDER
}

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

# ============================================================
# CONTROLLER-SPECIFIC SETUP GOES HERE
# ============================================================
CYCLE_LENGTH = 120
MIN_CHANGE_TIME = 16

HALF_CYCLE = CYCLE_LENGTH // 2
GREEN_END_1 = HALF_CYCLE - 5
YELLOW_END_1 = HALF_CYCLE - 1
GREEN_END_2 = CYCLE_LENGTH - 5
YELLOW_END_2 = CYCLE_LENGTH - 1

sim_module = [0] * NUM_TLS
x_i = [[] for _ in range(NUM_TLS)]


def get_lane_queue(lane_id):

    if lane_id is None or lane_id == "":
        return 0

    return sum(
        1
        for veh in traci.lane.getLastStepVehicleIDs(lane_id)
        if traci.vehicle.getSpeed(veh) < 0.1
    )
def get_movement_pressures(tls):
    """
    MPLight observation component:
    one pressure value for each controlled movement.
    """

    controlled_links = (
        traci.trafficlight.getControlledLinks(tls)
    )

    movement_pressures = []

    for link_group in controlled_links:

        if not link_group:
            movement_pressures.append(0)
            continue

        link = link_group[0]

        incoming_lane = link[0]
        outgoing_lane = link[1]

        incoming_queue = get_lane_queue(
            incoming_lane
        )

        outgoing_queue = get_lane_queue(
            outgoing_lane
        )

        movement_pressures.append(
            incoming_queue - outgoing_queue
        )

    return movement_pressures

def get_MPLight_state(tls):
    """
    12 movement pressures + current phase.

    Phase:
        0 = NS
        1 = EW
    """

    movement_pressures = get_movement_pressures(tls)

    current_state = (
        traci.trafficlight
        .getRedYellowGreenState(tls)
    )

    if current_state == PHASE_NS:

        current_phase = 0
        last_green_phase[tls] = 0

    elif current_state == PHASE_EW:

        current_phase = 1
        last_green_phase[tls] = 1

    else:

        current_phase = last_green_phase[tls]

    state = movement_pressures + [current_phase]

    if len(state) != 13:
        raise ValueError(
            f"{tls}: expected MPLight state length 13, got {len(state)} "
            f"({len(movement_pressures)} movement pressures)"
        )

    return state

def mplight_decision(tls):

    state = get_MPLight_state(tls)

    action = agent.select_action(state)

    # MPLight:
    # action 0 = NS
    # action 1 = EW
    #
    # wrapper:
    # +1 = NS
    # -1 = EW

    return 1 if action == 0 else -1

def sim_step():
    """
    Advance SUMO by one second and collect the same Seattle measurement
    framing used by the official 3x3 QAOA Seattle evaluator.
    """
    traci.simulationStep()
    t = traci.simulation.getTime()

    local_time = int(t % HOUR_SECONDS)

    for veh in traci.simulation.getDepartedIDList():
        if local_time >= WARMUP_TIME:
            hour = int(t // HOUR_SECONDS)

            if 0 <= hour < NUM_HOURS:
                depart_time[veh] = t
                depart_hour[veh] = hour
                last_waiting_time[veh] = 0.0
                measured_departures_by_hour[hour] += 1

    for veh in traci.vehicle.getIDList():
        if veh in depart_time:
            last_waiting_time[veh] = (
                traci.vehicle.getAccumulatedWaitingTime(veh)
            )

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

    return int(t)

def controller_step(current_time):

    # --------------------------------------------------------
    # 1. MPLight desired phase update
    # --------------------------------------------------------
    for tls in TLS_ORDER:

        tls_index = TLS_ORDER.index(tls)

        # Initialize desired phase from current signal state
        if len(x_i[tls_index]) == 0:

            current_state = (
                traci.trafficlight
                .getRedYellowGreenState(tls)
            )

            if current_state == PHASE_EW:
                x_i[tls_index].append(-1)

            else:
                x_i[tls_index].append(1)

        # New MPLight decision every 10 seconds
        elif current_time % DECISION_INTERVAL == 0:

            decision = mplight_decision(tls)

            x_i[tls_index].append(decision)

    # --------------------------------------------------------
    # 2. Apply signal logic: regular intersections
    # --------------------------------------------------------
    for tls in TLS_REG:

        tls_index = TLS_ORDER.index(tls)

        if (
            sim_module[tls_index] >= 0
            and sim_module[tls_index] < GREEN_END_1
        ):

            traci.trafficlight.setRedYellowGreenState(
                tls,
                PHASE_NS
            )

            if (
                sim_module[tls_index] >= MIN_CHANGE_TIME
                and x_i[tls_index][-1] == -1
            ):

                sim_module[tls_index] = GREEN_END_1

            else:

                sim_module[tls_index] += 1

        elif (
            sim_module[tls_index] >= GREEN_END_1
            and sim_module[tls_index] < YELLOW_END_1
        ):

            traci.trafficlight.setRedYellowGreenState(
                tls,
                YELLOW_NS_TO_EW
            )

            sim_module[tls_index] += 1

        elif (
            sim_module[tls_index] >= YELLOW_END_1
            and sim_module[tls_index] < HALF_CYCLE
        ):

            traci.trafficlight.setRedYellowGreenState(
                tls,
                ALL_RED
            )

            sim_module[tls_index] += 1

        elif (
            sim_module[tls_index] >= HALF_CYCLE
            and sim_module[tls_index] < GREEN_END_2
        ):

            traci.trafficlight.setRedYellowGreenState(
                tls,
                PHASE_EW
            )

            if (
                sim_module[tls_index] >= (
                    MIN_CHANGE_TIME + HALF_CYCLE
                )
                and x_i[tls_index][-1] == 1
            ):

                sim_module[tls_index] = GREEN_END_2

            else:

                sim_module[tls_index] += 1

        elif (
            sim_module[tls_index] >= GREEN_END_2
            and sim_module[tls_index] < YELLOW_END_2
        ):

            traci.trafficlight.setRedYellowGreenState(
                tls,
                YELLOW_EW_TO_NS
            )

            sim_module[tls_index] += 1

        elif (
            sim_module[tls_index] >= YELLOW_END_2
            and sim_module[tls_index] < CYCLE_LENGTH
        ):

            traci.trafficlight.setRedYellowGreenState(
                tls,
                ALL_RED
            )

            sim_module[tls_index] = 0

    # --------------------------------------------------------
    # 3. Apply signal logic: inverted intersections
    # --------------------------------------------------------
    for tls in TLS_INVERT:

        tls_index = TLS_ORDER.index(tls)

        if (
            sim_module[tls_index] >= 0
            and sim_module[tls_index] < GREEN_END_1
        ):

            traci.trafficlight.setRedYellowGreenState(
                tls,
                PHASE_EW
            )

            if (
                sim_module[tls_index] >= MIN_CHANGE_TIME
                and x_i[tls_index][-1] == 1
            ):

                sim_module[tls_index] = GREEN_END_1

            else:

                sim_module[tls_index] += 1

        elif (
            sim_module[tls_index] >= GREEN_END_1
            and sim_module[tls_index] < YELLOW_END_1
        ):

            traci.trafficlight.setRedYellowGreenState(
                tls,
                YELLOW_EW_TO_NS
            )

            sim_module[tls_index] += 1

        elif (
            sim_module[tls_index] >= YELLOW_END_1
            and sim_module[tls_index] < HALF_CYCLE
        ):

            traci.trafficlight.setRedYellowGreenState(
                tls,
                ALL_RED
            )

            sim_module[tls_index] += 1

        elif (
            sim_module[tls_index] >= HALF_CYCLE
            and sim_module[tls_index] < GREEN_END_2
        ):

            traci.trafficlight.setRedYellowGreenState(
                tls,
                PHASE_NS
            )

            if (
                sim_module[tls_index] >= (
                    MIN_CHANGE_TIME + HALF_CYCLE
                )
                and x_i[tls_index][-1] == -1
            ):

                sim_module[tls_index] = GREEN_END_2

            else:

                sim_module[tls_index] += 1

        elif (
            sim_module[tls_index] >= GREEN_END_2
            and sim_module[tls_index] < YELLOW_END_2
        ):

            traci.trafficlight.setRedYellowGreenState(
                tls,
                YELLOW_NS_TO_EW
            )

            sim_module[tls_index] += 1

        elif (
            sim_module[tls_index] >= YELLOW_END_2
            and sim_module[tls_index] < CYCLE_LENGTH
        ):

            traci.trafficlight.setRedYellowGreenState(
                tls,
                ALL_RED
            )

            sim_module[tls_index] = 0


try:
    while traci.simulation.getTime() < END_TIME:
        current_time = sim_step()

        controller_step(current_time)

        if current_time % HOUR_SECONDS == 0:
            print(
                f"t={current_time:5d} s | "
                f"hour={min(current_time // HOUR_SECONDS, 24):02d} | "
                f"measured_departed={sum(measured_departures_by_hour.values())} | "
                f"measured_completed={sum(completed_vehicles_by_hour.values())} | "
                f"active={traci.vehicle.getIDCount()}"
            )

finally:
    traci.close()


# -----------------------
# CANONICAL RESULTS
# -----------------------
print("\n===== 3x3 SEATTLE PERFORMANCE METRICS =====")
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
