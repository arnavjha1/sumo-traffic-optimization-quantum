import traci
from collections import defaultdict

# =======================
# CONFIG
# =======================
SUMO_BINARY = "sumo-gui"
SUMO_CONFIG = "sim.sumocfg"
END_TIME = 600

LEFT_MAX_TIME = 15          # seconds
EW_QUEUE_THRESHOLD = 12      # cars
NS_QUEUE_THRESHOLD = 12


# =======================
# START SUMO
# =======================
traci.start([SUMO_BINARY, "-c", SUMO_CONFIG])


# =======================
# TLS PHASE INDICES
# (CHANGE THESE IF NEEDED)
# =======================
PHASE_NS_LEFT = 0
PHASE_NS_STRAIGHT = 1
PHASE_EW_LEFT = 2
PHASE_EW_STRAIGHT = 3

TLS_ID = traci.trafficlight.getIDList()[0]

# =======================
# METRICS
# =======================
depart_time = {}
route_of = {}
last_waiting_time = {}

travel_times = defaultdict(list)
waiting_times = defaultdict(list)
throughput = defaultdict(int)

# =======================
# HELPERS
# =======================
def stopped_cars_in_lanes(lanes):
    count = 0
    for lane in lanes:
        for v in traci.lane.getLastStepVehicleIDs(lane):
            if traci.vehicle.getSpeed(v) < 0.1:
                count += 1
    return count

def get_lanes(direction, lane_type):
    """
    direction: 'NS' or 'EW'
    lane_type: 'left' or 'right'
    """
    lanes = []
    for lane in traci.trafficlight.getControlledLanes(TLS_ID):
        if direction in lane and lane_type in lane:
            lanes.append(lane)
    return lanes

state = "NS_LEFT"
state_start_time = 0

# =======================
# SIM LOOP
# =======================
while traci.simulation.getTime() < END_TIME:
    traci.simulationStep()
    t = traci.simulation.getTime()

    # -------------------
    # VEHICLE METRICS
    # -------------------
    for veh in traci.simulation.getDepartedIDList():
        depart_time[veh] = t
        route_of[veh] = traci.vehicle.getRouteID(veh)
        last_waiting_time[veh] = 0.0

    for veh in traci.vehicle.getIDList():
        last_waiting_time[veh] = traci.vehicle.getAccumulatedWaitingTime(veh)

    for veh in traci.simulation.getArrivedIDList():
        if veh in depart_time:
            r = route_of[veh]
            travel_times[r].append(t - depart_time[veh])
            waiting_times[r].append(last_waiting_time.get(veh, 0))
            throughput[r] += 1

            depart_time.pop(veh, None)
            route_of.pop(veh, None)
            last_waiting_time.pop(veh, None)

    # -------------------
    # QUEUES
    # -------------------
    ns_left = stopped_cars_in_lanes(get_lanes("NS", "left"))
    ns_right = stopped_cars_in_lanes(get_lanes("NS", "right"))
    ew_left = stopped_cars_in_lanes(get_lanes("EW", "left"))
    ew_right = stopped_cars_in_lanes(get_lanes("EW", "right"))

    # -------------------
    # STATE MACHINE
    # -------------------
    elapsed = t - state_start_time

    if state == "NS_LEFT":
        traci.trafficlight.setPhase(TLS_ID, PHASE_NS_LEFT)

        if ns_left == 0 or elapsed >= LEFT_MAX_TIME:
            state = "NS_STRAIGHT"
            state_start_time = t

    elif state == "NS_STRAIGHT":
        traci.trafficlight.setPhase(TLS_ID, PHASE_NS_STRAIGHT)

        if ew_left + ew_right >= EW_QUEUE_THRESHOLD:
            state = "EW_LEFT"
            state_start_time = t

    elif state == "EW_LEFT":
        traci.trafficlight.setPhase(TLS_ID, PHASE_EW_LEFT)

        if ew_left == 0 or elapsed >= LEFT_MAX_TIME:
            state = "EW_STRAIGHT"
            state_start_time = t

    elif state == "EW_STRAIGHT":
        traci.trafficlight.setPhase(TLS_ID, PHASE_EW_STRAIGHT)

        if ns_left + ns_right >= NS_QUEUE_THRESHOLD:
            state = "NS_LEFT"
            state_start_time = t

traci.close()

# =======================
# RESULTS
# =======================
print("\n===== RESULTS =====")

for r, times in travel_times.items():
    print(f"{r}: avg travel {sum(times)/len(times):.2f}s, throughput {throughput[r]}")

