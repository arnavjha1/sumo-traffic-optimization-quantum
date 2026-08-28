# CO LIGHT
import traci
import torch
from collections import defaultdict
from agent import CoLightAgent

SUMO_BINARY = "sumo-gui"

import sys
ALPHA_INDEX = int(sys.argv[1]) if len(sys.argv) > 1 else 7
SUMO_CONFIG = f"grid_3x3/sim3x3_a{ALPHA_INDEX}.sumocfg"
MODEL_PATH = "CoLight_model_v1.pt"
END_TIME = 600

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

def compute_avg(route_list, data_dict):
    values = []

    for route in route_list:
        values.extend(
            data_dict.get(route, [])
        )

    if not values:
        return None

    return sum(values) / len(values)


def compute_throughput(route_list, throughput):
    return sum(
        throughput.get(route, 0)
        for route in route_list
    )


def print_episode_metrics(
    queue_lengths,
    travel_times,
    waiting_times,
    throughput,
):
    print("\n===== PERFORMANCE METRICS =====")

    print("\nAverage Queue Length per TLS per Side/Lane:")
    lane_labels = ["Right", "Straight", "Left"]

    for tls_index, tls in enumerate(TLS_ORDER):
        print(f"\n  {tls}:")

        for side_index in range(NUM_SIDES):
            print(
                f"    Side {side_index}: ",
                end=""
            )

            for lane_index in range(NUM_LANES):
                data = queue_lengths[
                    tls_index
                ][side_index][lane_index]

                avg = (
                    sum(data) / len(data)
                    if data
                    else 0
                )

                print(
                    f"{lane_labels[lane_index]}={avg:.1f} ",
                    end=""
                )

            print()

    print("\nCoLight")

    print("\nAverage Travel Time:")

    avg_two = compute_avg(TWO_TURNS, travel_times)
    avg_one = compute_avg(ONE_TURN, travel_times)
    avg_none = compute_avg(NO_TURNS, travel_times)
    avg_all = compute_avg(ALL_ROUTES, travel_times)

    print(
        f"  Two Turns: {avg_two:.2f} s"
        if avg_two is not None
        else "  Two Turns: N/A"
    )
    print(
        f"  One Turn:  {avg_one:.2f} s"
        if avg_one is not None
        else "  One Turn: N/A"
    )
    print(
        f"  No Turns:  {avg_none:.2f} s"
        if avg_none is not None
        else "  No Turns: N/A"
    )
    print(
        f"  Overall:   {avg_all:.2f} s"
        if avg_all is not None
        else "  Overall: N/A"
    )

    print("\nAverage Waiting Time:")

    avg_two = compute_avg(TWO_TURNS, waiting_times)
    avg_one = compute_avg(ONE_TURN, waiting_times)
    avg_none = compute_avg(NO_TURNS, waiting_times)
    avg_all = compute_avg(ALL_ROUTES, waiting_times)

    print(
        f"  Two Turns: {avg_two:.2f} s"
        if avg_two is not None
        else "  Two Turns: N/A"
    )
    print(
        f"  One Turn:  {avg_one:.2f} s"
        if avg_one is not None
        else "  One Turn: N/A"
    )
    print(
        f"  No Turns:  {avg_none:.2f} s"
        if avg_none is not None
        else "  No Turns: N/A"
    )
    print(
        f"  Overall:   {avg_all:.2f} s"
        if avg_all is not None
        else "  Overall: N/A"
    )

    print("\nThroughput:")

    thr_two = compute_throughput(
        TWO_TURNS,
        throughput
    )
    thr_one = compute_throughput(
        ONE_TURN,
        throughput
    )
    thr_none = compute_throughput(
        NO_TURNS,
        throughput
    )
    thr_all = compute_throughput(
        ALL_ROUTES,
        throughput
    )

    print(f"  Two Turns: {thr_two}")
    print(f"  One Turn:  {thr_one}")
    print(f"  No Turns:  {thr_none}")
    print(f"  Overall:   {thr_all}")



# ============================================================
# FROZEN COLIGHT EVALUATION
# ============================================================

def run_evaluation(agent):
    traci.start([
        SUMO_BINARY,
        "-c",
        SUMO_CONFIG,
    ])

    try:
        # -----------------------
        # FORCE MANUAL TLS CONTROL
        # -----------------------
        for tls in TLS_ORDER:
            traci.trafficlight.setProgram(
                tls,
                "0"
            )
            traci.trafficlight.setPhaseDuration(
                tls,
                999999
            )

        # Same initial arrangement used during CoLight training.
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
        # METRIC DATA STRUCTURES
        # -----------------------
        depart_time = {}
        route_of = {}
        last_waiting_time = {}

        travel_times = defaultdict(list)
        waiting_times = defaultdict(list)
        throughput = defaultdict(int)

        queue_lengths = [
            [
                [[] for _ in range(NUM_LANES)]
                for _ in range(NUM_SIDES)
            ]
            for _ in range(NUM_TLS)
        ]

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

            # Vehicles that just departed
            for veh in traci.simulation.getDepartedIDList():
                depart_time[veh] = t
                route_of[veh] = traci.vehicle.getRouteID(veh)
                last_waiting_time[veh] = 0.0

            # Update accumulated waiting times
            for veh in traci.vehicle.getIDList():
                last_waiting_time[veh] = (
                    traci.vehicle.getAccumulatedWaitingTime(veh)
                )

            # Vehicles that just arrived
            for veh in traci.simulation.getArrivedIDList():
                if veh not in depart_time:
                    continue

                route = route_of[veh]
                travel_time = t - depart_time[veh]
                waiting_time = last_waiting_time.get(
                    veh,
                    0.0
                )

                travel_times[route].append(travel_time)
                waiting_times[route].append(waiting_time)
                throughput[route] += 1

                depart_time.pop(veh, None)
                route_of.pop(veh, None)
                last_waiting_time.pop(veh, None)

            # Queue history used for final reporting
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
                            queue = get_lane_queue(lane_id)
                        else:
                            queue = 0

                        queue_lengths[
                            tls_index
                        ][side_index][lane_index].append(
                            queue
                        )

        print("\n===== FROZEN COLIGHT EVALUATION =====")
        print(f"Model: {MODEL_PATH}")
        print(f"Evaluation epsilon: {agent.epsilon:.4f}")
        print(f"Simulation duration: {END_TIME} s")

        while traci.simulation.getTime() < END_TIME:
            # Advance SUMO under the most recently selected actions.
            sim_step()

            current_time = int(traci.simulation.getTime())

            # The t=END_TIME step has already been included in the metrics.
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

                # epsilon == 0 in evaluation mode, so these are fully
                # deterministic graph-aware actions from the frozen model.
                graph_actions = agent.select_actions(
                    all_states
                )

                # Preserve the same signal-transition constraints used
                # during training.
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
                print("\nAttention weights:")
                print(attention_weights)
                print("\nAttention row sums:")
                print(attention_weights.sum(dim=-1))
                print("\nGraph actions from Q-values:")
                print(graph_actions_debug)
                print("===== END ATTENTION CHECK =====\n")

            # Apply the most recently selected desired phase every SUMO
            # second. This is the same state machine used during training.
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

        print_episode_metrics(
            queue_lengths,
            travel_times,
            waiting_times,
            throughput,
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
