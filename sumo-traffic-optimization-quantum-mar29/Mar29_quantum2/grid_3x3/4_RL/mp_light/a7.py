import traci
import sys
from agent import MPLightAgent

# -----------------------
# SIMULATION SETTINGS
# -----------------------
SUMO_BINARY = "sumo"

ALPHA_INDEX = int(sys.argv[1]) if len(sys.argv) > 1 else 7
SUMO_CONFIG = f"grid_3x3/sim3x3_a{ALPHA_INDEX}.sumocfg"
END_TIME = 600

MODEL_PATH = "MPLight_model_v1.pt"
DECISION_INTERVAL = 10

ROUTE_FILE = f"grid_3x3/routes_3x3/routes3x3_a{ALPHA_INDEX}.rou.xml"

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

CYCLE_LENGTH = 120

# -----------------------
# SUMO COMMAND
# -----------------------
sumo_cmd = [
    SUMO_BINARY,
    "-c", SUMO_CONFIG,
    "--route-files", ROUTE_FILE,
    "--end", str(END_TIME),
]

traci.start(sumo_cmd)

# -----------------------
# LOAD FROZEN MPLIGHT MODEL
# -----------------------
agent = MPLightAgent()
agent.load(MODEL_PATH)
agent.set_evaluation_mode()

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


last_green_phase = {
    tls: (0 if tls in TLS_REG else 1)
    for tls in TLS_ORDER
}

# -----------------------
# DATA STRUCTURES
# -----------------------
depart_time = {}
last_waiting_time = {}

travel_times = []
waiting_times = []

total_departed = 0
total_arrived = 0

NUM_TLS = 9
sim_module = [0] * NUM_TLS

# -----------------------
# SIMULATION STEP
# -----------------------
def simStep(num_times=1):
    global total_departed, total_arrived

    for _ in range(num_times):
        traci.simulationStep()
        t = traci.simulation.getTime()

        # Vehicles that just departed
        for veh in traci.simulation.getDepartedIDList():
            depart_time[veh] = t
            last_waiting_time[veh] = 0.0
            total_departed += 1

        # Update accumulated waiting times
        for veh in traci.vehicle.getIDList():
            if veh in depart_time:
                last_waiting_time[veh] = (
                    traci.vehicle.getAccumulatedWaitingTime(veh)
                )

        # Vehicles that just arrived
        for veh in traci.simulation.getArrivedIDList():
            if veh in depart_time:
                travel_time = t - depart_time[veh]
                waiting_time = last_waiting_time.get(veh, 0.0)

                travel_times.append(travel_time)
                waiting_times.append(waiting_time)

                total_arrived += 1

                depart_time.pop(veh, None)
                last_waiting_time.pop(veh, None)

    return traci.simulation.getTime()
# =============================
# MPLIGHT SPECIFIC CODE
# =============================

PHASE_NS = "GGgrrrGGgrrr"
PHASE_EW = "rrrGGgrrrGGg"

MIN_CHANGE_TIME = 16

HALF_CYCLE = CYCLE_LENGTH // 2
GREEN_END_1 = HALF_CYCLE - 5
YELLOW_END_1 = HALF_CYCLE - 1

GREEN_END_2 = CYCLE_LENGTH - 5
YELLOW_END_2 = CYCLE_LENGTH - 1


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

    controlled_links = traci.trafficlight.getControlledLinks(tls)
    movement_pressures = []

    for link_group in controlled_links:

        if not link_group:
            movement_pressures.append(0)
            continue

        link = link_group[0]

        incoming_lane = link[0]
        outgoing_lane = link[1]

        incoming_queue = get_lane_queue(incoming_lane)
        outgoing_queue = get_lane_queue(outgoing_lane)

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

# -----------------------
# SIMULATION LOOP
# -----------------------
sim_module = [0] * NUM_TLS
x_i = [[] for _ in range(NUM_TLS)]

print("\n===== 3x3 MPLIGHT SATURATED TEST =====")
print(f"Alpha case: a{ALPHA_INDEX} ({ALPHA_INDEX / 10:.1f})")
print(f"Route file: {ROUTE_FILE}")
print(f"Simulation duration: {END_TIME} s")

while traci.simulation.getTime() < END_TIME:
    simStep()
    current_time = int(traci.simulation.getTime())


    for tls in TLS_ORDER:
        tls_index = TLS_ORDER.index(tls)

        # Initialize desired phase
        if len(x_i[tls_index]) == 0:
            current_state = traci.trafficlight.getRedYellowGreenState(tls)
            if current_state == PHASE_EW:
                x_i[tls_index].append(-1)
            else:
                x_i[tls_index].append(1)

        # New MPLight decision every 10 seconds
        elif current_time % DECISION_INTERVAL == 0:
            decision = mplight_decision(tls)
            x_i[tls_index].append(decision)


    for tls in TLS_REG:
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

    if current_time % 100 == 0:
        print(
            f"t={current_time:3d} s | "
            f"departed={total_departed} | "
            f"arrived={total_arrived} | "
            f"active={traci.vehicle.getIDCount()}"
        )

traci.close()

# -----------------------
# RESULTS
# -----------------------
avg_travel_time = (
    sum(travel_times) / len(travel_times)
    if travel_times
    else 0.0
)

avg_waiting_time = (
    sum(waiting_times) / len(waiting_times)
    if waiting_times
    else 0.0
)

print("\n===== PERFORMANCE METRICS =====")
print(f"Alpha: {ALPHA_INDEX / 10:.1f}")
print(f"Average Travel Time: {avg_travel_time:.2f} s")
print(f"Average Waiting Time: {avg_waiting_time:.2f} s")
print(f"Throughput: {total_arrived}")
print(f"Vehicles inserted: {total_departed}")
print(
    f"Vehicles still in network at t={END_TIME}: "
    f"{total_departed - total_arrived}"
)
