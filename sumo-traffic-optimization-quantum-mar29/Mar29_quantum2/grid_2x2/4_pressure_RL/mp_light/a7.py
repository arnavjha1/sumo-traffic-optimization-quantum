import traci
from collections import defaultdict
from agent import MPLightAgent

SUMO_BINARY = "sumo"
SUMO_CONFIG = "sim2x2_a7.sumocfg"
END_TIME = 600

NUM_RUNS = 1

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

NUM_TLS = 4
NUM_SIDES = 4
NUM_LANES = 3

PHASE_NS = "GGgrrrGGgrrr"
PHASE_EW = "rrrGGgrrrGGg"

YELLOW_NS_TO_EW = "yyyrrryyyrrr"
YELLOW_EW_TO_NS = "rrryyyrrryyy"
ALL_RED = "rrrrrrrrrrrr"

MIN_CHANGE_TIME = 12
MAX_GREEN_TIME = 55
YELLOW_TIME = 4
ALL_RED_TIME = 1


# ============================================================
# MPLight STATE / REWARD
# ============================================================

def get_lane_queue(lane_id):
    if lane_id is None or lane_id == "":
        return 0

    return sum(
        1
        for veh in traci.lane.getLastStepVehicleIDs(lane_id)
        if traci.vehicle.getSpeed(veh) < 0.1
    )

def get_movement_pressures(tls):

    controlled_links = traci.trafficlight.getControlledLinks(tls)

    movement_pressures = []

    for signal_index, link_group in enumerate(controlled_links):

        # Normally there is one controlled link per signal index
        # in your network.
        link = link_group[0]

        incoming_lane = link[0]
        outgoing_lane = link[1]

        incoming_queue = get_lane_queue(incoming_lane)
        outgoing_queue = get_lane_queue(outgoing_lane)

        pressure = incoming_queue - outgoing_queue

        movement_pressures.append(pressure)

    return movement_pressures

def get_intersection_pressure(tls):

    controlled_links = traci.trafficlight.getControlledLinks(tls)

    incoming_lanes = set()
    outgoing_lanes = set()

    for link_group in controlled_links:
        for link in link_group:

            incoming_lane = link[0]
            outgoing_lane = link[1]

            incoming_lanes.add(incoming_lane)
            outgoing_lanes.add(outgoing_lane)

    total_incoming_queue = sum(
        get_lane_queue(lane)
        for lane in incoming_lanes
    )

    total_outgoing_queue = sum(
        get_lane_queue(lane)
        for lane in outgoing_lanes
    )

    pressure = abs(
        total_incoming_queue
        - total_outgoing_queue
    )

    return pressure

def get_MPLight_state(tls, last_green_phase):

    # Get the 12 movement-level pressures
    movement_pressures = get_movement_pressures(tls)

    # Determine which green phase is currently active
    current_state = traci.trafficlight.getRedYellowGreenState(tls)

    if current_state == PHASE_NS:
        current_phase = 0

    elif current_state == PHASE_EW:
        current_phase = 1

    else:
        # During yellow/all-red, remember the previous green phase
        current_phase = last_green_phase[tls]

    # MPLight state:
    # 12 movement pressures + current phase
    return movement_pressures + [current_phase]

def get_MPLight_reward(tls, last_green_phase):

    pressure = get_intersection_pressure(tls)

    return -pressure


# ============================================================
# SIGNAL TRANSITION LOGIC
# ============================================================

def choose_effective_action(
    agent,
    state,
    current_phase,
    signal_mode,
    green_elapsed,
    pending_phase,
):
    """
    The agent only makes a new decision when the signal is in a green
    state and the minimum green time has elapsed.

    During minimum-green or transition periods, the environment holds
    the required action. MAX_GREEN_TIME prevents indefinite starvation.
    """

    if signal_mode != "green":
        if pending_phase is not None:
            return pending_phase
        return current_phase

    if green_elapsed < MIN_CHANGE_TIME:
        return current_phase

    if green_elapsed >= MAX_GREEN_TIME:
        return 1 - current_phase

    return agent.select_action(state)


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

    print("\nMPLight")

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
# TRAINING EPISODE
# ============================================================

def run_episode(agent, episode):
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

        print("\n===== DEBUG: MOVEMENT PRESSURES FOR A0 =====")

        pressures = get_movement_pressures("A0")

        for i, pressure in enumerate(pressures):
            print(f"Movement {i}: pressure = {pressure}")

        print("===== END DEBUG =====\n")

        # Initial signal arrangement matches your previous setup.
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
        # EPISODE DATA STRUCTURES
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

        previous_states = [None] * NUM_TLS
        previous_actions = [None] * NUM_TLS

        episode_losses = []
        episode_rewards = []

        def sim_step():
            traci.simulationStep()
            t = traci.simulation.getTime()

            # Vehicles that just departed
            for veh in traci.simulation.getDepartedIDList():
                depart_time[veh] = t
                route_of[veh] = traci.vehicle.getRouteID(veh)
                last_waiting_time[veh] = 0.0

            # Update waiting times
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

                travel_times[route].append(
                    travel_time
                )

                waiting_times[route].append(
                    waiting_time
                )

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

        print(
            f"\nStarting episode {episode + 1}/{NUM_RUNS} "
            f"with epsilon={agent.epsilon:.4f}"
        )

        while traci.simulation.getTime() < END_TIME:
            # ----------------------------------------------------
            # 1. Advance SUMO under the actions selected last step
            # ----------------------------------------------------
            sim_step()

            if traci.simulation.getTime() == 100:

                print("\n===== MPLIGHT STATE CHECK AT t=100 =====")

                for tls in TLS_ORDER:

                    state = get_MPLight_state(
                        tls,
                        last_green_phase
                    )

                    pressure = get_intersection_pressure(tls)

                    reward = get_MPLight_reward(
                        tls,
                        last_green_phase
                    )

                    print(f"\nTLS: {tls}")
                    print(f"State: {state}")
                    print(f"State length: {len(state)}")
                    print(f"Intersection pressure: {pressure}")
                    print(f"Reward: {reward}")

                state = get_MPLight_state(
                    "A0",
                    last_green_phase
                )

                movement_pressures = state[:12]

                ns_pressures = [
                    movement_pressures[i]
                    for i in [0, 1, 2, 6, 7, 8]
                ]

                ew_pressures = [
                    movement_pressures[i]
                    for i in [3, 4, 5, 9, 10, 11]
                ]

                print("\nA0 NS movement pressures:")
                print(ns_pressures)

                print("A0 EW movement pressures:")
                print(ew_pressures)

                print("NS movement count:", len(ns_pressures))
                print("EW movement count:", len(ew_pressures))

                import torch

                test_state = torch.tensor(
                    state,
                    dtype=torch.float32
                ).unsqueeze(0)

                with torch.no_grad():
                    test_q_values = agent.model(test_state)

                print("\nA0 Q-values:")
                print(test_q_values)

                print("Q-value shape:")
                print(test_q_values.shape)

                print("\n===== END STATE CHECK =====\n")

            done = (
                traci.simulation.getTime()
                >= END_TIME
            )

            # ----------------------------------------------------
            # 2. Observe s_(t+1), reward, and store old experience
            # ----------------------------------------------------
            stored_experience = False

            for idx, tls in enumerate(TLS_ORDER):
                if previous_states[idx] is None:
                    continue

                next_state = get_MPLight_state(
                    tls,
                    last_green_phase
                )

                reward = get_MPLight_reward(
                    tls,
                    last_green_phase
                )

                episode_rewards.append(reward)

                agent.remember(
                    previous_states[idx],
                    previous_actions[idx],
                    reward,
                    next_state,
                    done,
                )

                stored_experience = True

            # One shared-network update per SUMO step.
            if stored_experience:
                loss = agent.train_step()

                if loss is not None:
                    episode_losses.append(loss)

            if done:
                break

            # ----------------------------------------------------
            # 3. Observe current state and choose the next action
            # ----------------------------------------------------
            for idx, tls in enumerate(TLS_ORDER):
                state = get_MPLight_state(
                    tls,
                    last_green_phase
                )

                action = choose_effective_action(
                    agent=agent,
                    state=state,
                    current_phase=current_green_phase[idx],
                    signal_mode=signal_mode[idx],
                    green_elapsed=green_elapsed[idx],
                    pending_phase=pending_phase[idx],
                )

                previous_states[idx] = state
                previous_actions[idx] = action

                # ------------------------------------------------
                # 4. Apply the chosen desired phase to the signal
                # ------------------------------------------------
                apply_signal_action(
                    tls=tls,
                    idx=idx,
                    desired_action=action,
                    current_green_phase=current_green_phase,
                    last_green_phase=last_green_phase,
                    signal_mode=signal_mode,
                    green_elapsed=green_elapsed,
                    transition_timer=transition_timer,
                    pending_phase=pending_phase,
                )

        agent.decay_epsilon()

        avg_loss = (
            sum(episode_losses) / len(episode_losses)
            if episode_losses
            else None
        )

        avg_reward = (
            sum(episode_rewards) / len(episode_rewards)
            if episode_rewards
            else None
        )

        loss_text = (
            f"{avg_loss:.6f}"
            if avg_loss is not None
            else "N/A"
        )

        reward_text = (
            f"{avg_reward:.6f}"
            if avg_reward is not None
            else "N/A"
        )

        print(
            f"Finished episode {episode + 1}: "
            f"epsilon={agent.epsilon:.4f}, "
            f"memory={len(agent.memory)}, "
            f"avg_loss={loss_text}, "
            f"avg_reward={reward_text}"
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
# TRAIN
# ============================================================

agent = MPLightAgent()

for episode in range(NUM_RUNS):
    run_episode(
        agent,
        episode
    )

agent.save(
    "MPLight_model.pt"
)

print(
    "\nTraining complete. Model saved to MPLight_model.pt"
)
