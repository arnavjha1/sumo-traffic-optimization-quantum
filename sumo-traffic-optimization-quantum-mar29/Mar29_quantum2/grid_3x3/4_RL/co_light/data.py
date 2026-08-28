"""
Canonical 3x3 Seattle CoLight evaluation.

Seattle measurement framing matches the already-run official 3x3 QAOA
experiment and the other 3x3 Seattle controllers:
- 24-hour simulation: 86,400 s
- 900-s measurement warm-up excluded at the start of every hour
- random departure offset: 0-60 s
- completed vehicles attributed to their departure hour
- no post-24h drain period

The frozen CoLight controller logic, graph, state representation, 10-second
decision interval, and signal-transition state machine are preserved from the
working 3x3 saturated evaluator.
"""

import traci
import torch
from collections import defaultdict
from agent import CoLightAgent

SUMO_BINARY = "sumo"
SUMO_CONFIG = "grid_3x3/sim3x3_data.sumocfg"

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

TLS_ORDER = [
    "A0", "A1", "A2",
    "B0", "B1", "B2",
    "C0", "C1", "C2",
]

TLS_REG = ["A1", "B1", "B2", "C0", "C1", "C2"]
TLS_INVERT = ["A0", "A2", "B0"]

ADJACENCY = [
    # A0 A1 A2 B0 B1 B2 C0 C1 C2

    [1, 1, 0, 1, 0, 0, 0, 0, 0],  # A0
    [1, 1, 1, 0, 1, 0, 0, 0, 0],  # A1
    [0, 1, 1, 0, 0, 1, 0, 0, 0],  # A2

    [1, 0, 0, 1, 1, 0, 1, 0, 0],  # B0
    [0, 1, 0, 1, 1, 1, 0, 1, 0],  # B1
    [0, 0, 1, 0, 1, 1, 0, 0, 1],  # B2

    [0, 0, 0, 1, 0, 0, 1, 1, 0],  # C0
    [0, 0, 0, 0, 1, 0, 1, 1, 1],  # C1
    [0, 0, 0, 0, 0, 1, 0, 1, 1],  # C2
]

ADJACENCY_TENSOR = torch.tensor(
    ADJACENCY,
    dtype=torch.float32
)


NUM_TLS = 9
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

    lane_vehicle_counts = get_lane_vehicle_counts(tls)

    if len(lane_vehicle_counts) != 12:
        raise ValueError(
            f"{tls}: expected 12 lane counts, got {len(lane_vehicle_counts)}"
        )

    current_state = traci.trafficlight.getRedYellowGreenState(tls)

    if current_state == PHASE_NS:
        current_phase = 0

    elif current_state == PHASE_EW:
        current_phase = 1

    else:
        current_phase = last_green_phase[tls]

    if current_phase == 0:
        phase_one_hot = [1, 0]
    else:
        phase_one_hot = [0, 1]

    state = lane_vehicle_counts + phase_one_hot

    if len(state) != 14:
        raise ValueError(
            f"{tls}: expected CoLight state length 14, got {len(state)}"
        )

    return state


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

# ============================================================
# FROZEN COLIGHT SEATTLE EVALUATION
# ============================================================

def run_evaluation(agent):
    traci.start([
        SUMO_BINARY,
        "-c", SUMO_CONFIG,
        "--random-depart-offset", str(RANDOM_DEPART_OFFSET),
    ])

    try:
        # -----------------------
        # FORCE MANUAL TLS CONTROL
        # -----------------------
        for tls in TLS_ORDER:
            traci.trafficlight.setProgram(tls, "0")
            traci.trafficlight.setPhaseDuration(tls, 999999)

        # Same initial arrangement used in the tested 3x3 CoLight evaluator.
        # 0 = NS green, 1 = EW green.
        initial_phases = [
            1, 0, 1,
            1, 0, 0,
            0, 0, 0,
        ]

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
            """
            Advance SUMO by one second and collect the same hourly Seattle
            measurement framing used by the official 3x3 QAOA evaluator.
            """
            traci.simulationStep()
            t = traci.simulation.getTime()

            local_time = int(t % HOUR_SECONDS)

            # Track only vehicles departing after the hourly 900-s warm-up.
            for veh in traci.simulation.getDepartedIDList():
                if local_time >= WARMUP_TIME:
                    hour = int(t // HOUR_SECONDS)

                    if 0 <= hour < NUM_HOURS:
                        depart_time[veh] = t
                        depart_hour[veh] = hour
                        last_waiting_time[veh] = 0.0
                        measured_departures_by_hour[hour] += 1

            # Update accumulated waiting time for measured active vehicles.
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

            return int(t)

        print("\n===== FROZEN COLIGHT 3x3 SEATTLE EVALUATION =====")
        print(f"Model: {MODEL_PATH}")
        print(f"Evaluation epsilon: {agent.epsilon:.4f}")
        print(f"Simulation duration: {END_TIME} s")
        print(f"Warm-up excluded: first {WARMUP_TIME} s of every hour")
        print(f"Random departure offset: 0-{RANDOM_DEPART_OFFSET} s")

        while traci.simulation.getTime() < END_TIME:
            # Advance SUMO under the most recently selected actions.
            current_time = sim_step()

            if current_time % HOUR_SECONDS == 0:
                print(
                    f"t={current_time:5d} s | "
                    f"hour={min(current_time // HOUR_SECONDS, 24):02d} | "
                    f"measured_departed={sum(measured_departures_by_hour.values())} | "
                    f"measured_completed={sum(completed_vehicles_by_hour.values())} | "
                    f"active={traci.vehicle.getIDCount()}"
                )

            # The END_TIME step has already been included in the metrics.
            if current_time >= END_TIME:
                break

            decision_time = (
                current_time % DECISION_INTERVAL == 0
            )

            # ----------------------------------------------------
            # FROZEN COLIGHT JOINT DECISION
            # ----------------------------------------------------
            if decision_time:
                all_states = [
                    get_CoLight_state(
                        tls,
                        last_green_phase
                    )
                    for tls in TLS_ORDER
                ]

                # epsilon == 0 in evaluation mode: frozen deterministic policy.
                graph_actions = agent.select_actions(
                    all_states
                )

                # Preserve the same signal-transition constraints used
                # in the working 3x3 evaluator.
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

            # ----------------------------------------------------
            # OPTIONAL FROZEN-MODEL ATTENTION CHECK AT t=100
            # ----------------------------------------------------
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
                print("\nAttention row sums:")
                print(attention_weights.sum(dim=-1))
                print("\nGraph actions from Q-values:")
                print(graph_actions_debug)
                print("===== END ATTENTION CHECK =====\n")

            # Apply the most recently selected desired phase every SUMO second.
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

        # -----------------------
        # CANONICAL SEATTLE RESULTS
        # -----------------------
        print("\n===== 3x3 COLIGHT SEATTLE PERFORMANCE METRICS =====")
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
            total_measured_departures = sum(
                measured_departures_by_hour.values()
            )

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
