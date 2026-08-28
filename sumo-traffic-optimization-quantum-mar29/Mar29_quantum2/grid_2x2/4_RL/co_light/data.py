# CO LIGHT
import traci
import torch
from collections import defaultdict
from agent import CoLightAgent

SUMO_BINARY = "sumo"
SUMO_CONFIG = "sim2x2_data.sumocfg"
MODEL_PATH = "CoLight_model_v1.pt"
END_TIME = 86400
WARMUP_TIME = 900
RANDOM_DEPART_OFFSET = 60

HOUR_SECONDS = 3600
NUM_HOURS = 24
# Frozen evaluation only: no replay, optimizer steps, epsilon decay, or model saving.


# -----------------------
# FIXED OUTPUT ORDER
# -----------------------
TWO_TURNS = [
    "r0", "r4", "r6", "r7", "r11", "r13", "r14", "r18", "r20", "r21",
    "r25", "r27", "r28", "r32", "r34", "r35", "r39", "r41", "r42",
    "r46", "r48", "r49", "r53", "r55"
]

ONE_TURN = [
    "r1", "r3", "r5", "r8", "r10", "r12", "r15", "r17", "r19", "r22",
    "r24", "r26", "r29", "r31", "r33", "r36", "r38", "r40", "r43",
    "r45", "r47", "r50", "r52", "r54"
]

NO_TURNS = [
    "r2", "r9", "r16", "r23", "r30", "r37", "r44", "r51"
]

ALL_ROUTES = TWO_TURNS + ONE_TURN + NO_TURNS

TLS_ORDER = ["A0", "A1", "B0", "B1"]
TLS_REG = ["A0", "A1", "B0"]
TLS_INVERT = ["B1"]

TLS_NEIGHBORS = {
    "A0": ["A0", "A1", "B0"],
    "A1": ["A1", "A0", "B1"],
    "B0": ["B0", "A0", "B1"],
    "B1": ["B1", "A1", "B0"],
}

ADJACENCY = [
    [1, 1, 1, 0], #A0=1, A1=1, B0=1, B1=0
    [1, 1, 0, 1],
    [1, 0, 1, 1],
    [0, 1, 1, 1],
]

ADJACENCY_TENSOR = torch.tensor(
    ADJACENCY,
    dtype=torch.float32
)


NUM_TLS = 4
NUM_SIDES = 4
NUM_LANES = 3

PHASE_NS = "GGgrrrGGgrrr"
PHASE_EW = "rrrGGgrrrGGg"

YELLOW_NS_TO_EW = "yyyrrryyyrrr"
YELLOW_EW_TO_NS = "rrryyyrrryyy"
ALL_RED = "rrrrrrrrrrrr"

# update constants to more closely reflect CoLight paper
MIN_CHANGE_TIME = 10
MAX_GREEN_TIME = 999999
YELLOW_TIME = 3
ALL_RED_TIME = 2
DECISION_INTERVAL = 10

# graph sanity check
print("\n===== COLIGHT GRAPH CHECK =====")

for i, tls in enumerate(TLS_ORDER):
    connected = [
        TLS_ORDER[j]
        for j in range(NUM_TLS)
        if ADJACENCY[i][j] == 1
    ]

    print(f"{tls}: {connected}")

print("===== END GRAPH CHECK =====\n")

# ============================================================
# CoLight STATE
# ============================================================

def get_lane_queue(lane_id):
    if lane_id is None or lane_id == "":
        return 0

    return sum(
        1
        for veh in traci.lane.getLastStepVehicleIDs(lane_id)
        if traci.vehicle.getSpeed(veh) < 0.1
    )

def get_lane_vehicle_count(lane_id):

    if lane_id is None or lane_id == "":
        return 0

    return traci.lane.getLastStepVehicleNumber(lane_id)


def get_lane_vehicle_counts(tls):

    lanes = traci.trafficlight.getControlledLanes(tls)

    # Remove duplicate lane IDs while preserving order.
    # The trained CoLight model expects these 12 lane-level counts
    # in the same order used during training.
    lanes = list(dict.fromkeys(lanes))

    return [
        get_lane_vehicle_count(lane)
        for lane in lanes
    ]


def get_side_queues(tls):

    lanes = traci.trafficlight.getControlledLanes(tls)

    # Remove duplicate lane IDs while preserving order
    lanes = list(dict.fromkeys(lanes))

    lanes_per_side = len(lanes) // NUM_SIDES

    side_queues = []

    for side_index in range(NUM_SIDES):

        start = side_index * lanes_per_side
        end = start + lanes_per_side

        side_lanes = lanes[start:end]

        total_queue = sum(
            get_lane_queue(lane)
            for lane in side_lanes
        )

        side_queues.append(total_queue)

    return side_queues


def get_CoLight_state(tls, last_green_phase):

    # Match the trainer exactly:
    # 12 lane-level vehicle counts + 2-value one-hot phase = 14 features.
    lane_vehicle_counts = get_lane_vehicle_counts(tls)

    current_state = traci.trafficlight.getRedYellowGreenState(tls)

    if current_state == PHASE_NS:
        current_phase = 0

    elif current_state == PHASE_EW:
        current_phase = 1

    else:
        # During yellow/all-red, use the most recent green phase.
        current_phase = last_green_phase[tls]

    if current_phase == 0:
        phase_one_hot = [1, 0]
    else:
        phase_one_hot = [0, 1]

    return lane_vehicle_counts + phase_one_hot


# ============================================================
# SIGNAL TRANSITION LOGIC
# ============================================================

def apply_signal_action(
    tls,
    idx,
    desired_action,
    current_green_phase,
    last_green_phase,
    signal_mode,
    green_elapsed,
    transition_timer,
    pending_phase,
):
    mode = signal_mode[idx]
    current_phase = current_green_phase[idx]

    if mode == "green":
        green_state = (
            PHASE_NS
            if current_phase == 0
            else PHASE_EW
        )

        traci.trafficlight.setRedYellowGreenState(
            tls,
            green_state
        )

        if (
            desired_action != current_phase
            and green_elapsed[idx] >= MIN_CHANGE_TIME
        ):
            pending_phase[idx] = desired_action
            signal_mode[idx] = "yellow"
            transition_timer[idx] = 1

            yellow_state = (
                YELLOW_NS_TO_EW
                if current_phase == 0
                else YELLOW_EW_TO_NS
            )

            traci.trafficlight.setRedYellowGreenState(
                tls,
                yellow_state
            )
        else:
            green_elapsed[idx] += 1

    elif mode == "yellow":
        yellow_state = (
            YELLOW_NS_TO_EW
            if current_phase == 0
            else YELLOW_EW_TO_NS
        )

        traci.trafficlight.setRedYellowGreenState(
            tls,
            yellow_state
        )

        transition_timer[idx] += 1

        if transition_timer[idx] >= YELLOW_TIME:
            signal_mode[idx] = "all_red"
            transition_timer[idx] = 0

    elif mode == "all_red":
        traci.trafficlight.setRedYellowGreenState(
            tls,
            ALL_RED
        )

        transition_timer[idx] += 1

        if transition_timer[idx] >= ALL_RED_TIME:
            current_green_phase[idx] = pending_phase[idx]
            last_green_phase[tls] = pending_phase[idx]

            pending_phase[idx] = None
            signal_mode[idx] = "green"
            transition_timer[idx] = 0
            green_elapsed[idx] = 0


# ============================================================
# METRICS
# ============================================================

# ============================================================
# FROZEN COLIGHT 2x2 SEATTLE EVALUATION
# ============================================================

def run_evaluation(agent):
    sumo_cmd = [
        SUMO_BINARY,
        "-c", SUMO_CONFIG,
        "--random-depart-offset", str(RANDOM_DEPART_OFFSET),
    ]

    traci.start(sumo_cmd)

    try:
        # -----------------------
        # FORCE MANUAL TLS CONTROL
        # -----------------------
        for tls in TLS_ORDER:
            traci.trafficlight.setProgram(tls, "0")
            traci.trafficlight.setPhaseDuration(tls, 999999)

        # Same initial arrangement used during CoLight training/evaluation.
        # 0 = NS green, 1 = EW green.
        initial_phases = [0, 0, 0, 1]

        for idx, tls in enumerate(TLS_ORDER):
            initial_state = (
                PHASE_NS
                if initial_phases[idx] == 0
                else PHASE_EW
            )
            traci.trafficlight.setRedYellowGreenState(
                tls,
                initial_state
            )

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

        # -----------------------
        # SIGNAL STATE
        # -----------------------
        current_green_phase = initial_phases.copy()

        last_green_phase = {
            tls: initial_phases[idx]
            for idx, tls in enumerate(TLS_ORDER)
        }

        signal_mode = [
            "green"
            for _ in range(NUM_TLS)
        ]

        green_elapsed = [0] * NUM_TLS
        transition_timer = [0] * NUM_TLS
        pending_phase = [None] * NUM_TLS
        desired_actions = initial_phases.copy()

        def sim_step():
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

        print("\n===== FROZEN COLIGHT 2x2 SEATTLE EVALUATION =====")
        print(f"Model: {MODEL_PATH}")
        print(f"Evaluation epsilon: {agent.epsilon:.4f}")
        print(f"Simulation duration: {END_TIME} s")
        print(f"Warm-up excluded: first {WARMUP_TIME} s of every hour")
        print(f"Random departure offset: 0-{RANDOM_DEPART_OFFSET} s")

        while traci.simulation.getTime() < END_TIME:
            current_time = sim_step()

            if current_time % HOUR_SECONDS == 0:
                print(
                    f"t={current_time:5d} s | "
                    f"hour={min(current_time // HOUR_SECONDS, 24):02d} | "
                    f"measured_departed={sum(measured_departures_by_hour.values())} | "
                    f"measured_completed={sum(completed_vehicles_by_hour.values())} | "
                    f"active={traci.vehicle.getIDCount()}"
                )

            # t=END_TIME has already been included in traffic metrics.
            if current_time >= END_TIME:
                break

            decision_time = (
                current_time % DECISION_INTERVAL == 0
            )

            if decision_time:
                all_states = [
                    get_CoLight_state(
                        tls,
                        last_green_phase
                    )
                    for tls in TLS_ORDER
                ]

                graph_actions = agent.select_actions(
                    all_states
                )

                for idx, tls in enumerate(TLS_ORDER):
                    proposed_action = graph_actions[idx]

                    if signal_mode[idx] != "green":
                        if pending_phase[idx] is not None:
                            action = pending_phase[idx]
                        else:
                            action = current_green_phase[idx]

                    elif green_elapsed[idx] < MIN_CHANGE_TIME:
                        action = current_green_phase[idx]

                    elif green_elapsed[idx] >= MAX_GREEN_TIME:
                        action = 1 - current_green_phase[idx]

                    else:
                        action = proposed_action

                    desired_actions[idx] = action

                if current_time <= 50:
                    print(
                        f"CoLight evaluation decision at t={current_time}"
                    )
                    print("Graph actions:", graph_actions)
                    print("Applied actions:", desired_actions)

            # Preserve the original frozen-model attention check.
            if current_time == 100:
                all_states = [
                    get_CoLight_state(
                        tls,
                        last_green_phase
                    )
                    for tls in TLS_ORDER
                ]

                all_states_tensor = torch.tensor(
                    all_states,
                    dtype=torch.float32
                ).unsqueeze(0)

                with torch.no_grad():
                    graph_q_values, attention_weights = (
                        agent.model(
                            all_states_tensor,
                            agent.adjacency,
                            return_attention=True
                        )
                    )

                graph_actions_debug = torch.argmax(
                    graph_q_values,
                    dim=2
                ).squeeze(0)

                print("\n===== FROZEN COLIGHT ATTENTION CHECK =====")
                print("All-state tensor shape:")
                print(all_states_tensor.shape)
                print("\nGraph Q-value shape:")
                print(graph_q_values.shape)
                print("\nAttention-weight shape:")
                print(attention_weights.shape)
                print("\nAttention weights:")
                print(attention_weights)
                print("\nAttention row sums:")
                print(attention_weights.sum(dim=-1))
                print("\nGraph actions from Q-values:")
                print(graph_actions_debug)
                print("===== END ATTENTION CHECK =====\n")

            # Same transition state machine used by the working 2x2 evaluator.
            for idx, tls in enumerate(TLS_ORDER):
                apply_signal_action(
                    tls=tls,
                    idx=idx,
                    desired_action=desired_actions[idx],
                    current_green_phase=current_green_phase,
                    last_green_phase=last_green_phase,
                    signal_mode=signal_mode,
                    green_elapsed=green_elapsed,
                    transition_timer=transition_timer,
                    pending_phase=pending_phase,
                )

        # Canonical Seattle output
        # -----------------------
        # CANONICAL SEATTLE RESULTS
        # -----------------------
        print("\n===== 2x2 COLIGHT SEATTLE PERFORMANCE METRICS =====")
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

    finally:
        traci.close()

# ============================================================
# LOAD FROZEN MODEL AND RUN ONCE
# ============================================================

agent = CoLightAgent(
    state_size=14,
    adjacency=ADJACENCY
)

agent.load(
    MODEL_PATH
)

agent.set_evaluation_mode()

print("\nFrozen CoLight model loaded.")
print(f"Evaluation epsilon: {agent.epsilon}")

run_evaluation(
    agent
)

print("\nCoLight evaluation complete.")
