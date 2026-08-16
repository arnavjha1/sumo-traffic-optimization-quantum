import traci
from collections import defaultdict

SUMO_BINARY = "sumo-gui"
SUMO_CONFIG = "sim2x2_a7.sumocfg"
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

SCOOT_REGIONS = {
    "R0": ["A0", "A1", "B0", "B1"]
}

SCOOT_NODES = {
    "A0": {
        "region": "R0",
        "neighbors": ["A1", "B0"]
    },

    "A1": {
        "region": "R0",
        "neighbors": ["A0", "B1"]
    },

    "B0": {
        "region": "R0",
        "neighbors": ["A0", "B1"]
    },

    "B1": {
        "region": "R0",
        "neighbors": ["A1", "B0"]
    }
}

SCOOT_CONNECTIONS = [
    ("A0", "A1"),
    ("A1", "A0"),

    ("A0", "B0"),
    ("B0", "A0"),

    ("A1", "B1"),
    ("B1", "A1"),

    ("B0", "B1"),
    ("B1", "B0")
]

# ==========================================================
# SCOOT VIRTUAL DETECTOR SETTINGS (simulation starts here)
# ==========================================================

traci.start([SUMO_BINARY, "-c", SUMO_CONFIG])
cycle_length = 120  # seconds


DETECTOR_POSITION = 15.0     # meters from start of lane
DETECTOR_ZONE_START = 10.0   # meters
DETECTOR_ZONE_END = 20.0     # meters

scoot_links = {}

for upstream_node, downstream_node in SCOOT_CONNECTIONS:

    link_id = f"{upstream_node}->{downstream_node}"

    scoot_links[link_id] = {
        "upstream_node": upstream_node,
        "downstream_node": downstream_node
    }

scoot_node_state = {}

for tls in TLS_ORDER:

    scoot_node_state[tls] = {
        "region": SCOOT_NODES[tls]["region"],
        "cycle_length": cycle_length,
        "offset": 0
    }

scoot_region_state = {}

for region_id, nodes in SCOOT_REGIONS.items():

    scoot_region_state[region_id] = {
        "nodes": nodes,
        "cycle_length": cycle_length
    }


def validate_scoot_network():

    print("\n===== SCOOT NETWORK CHECK =====")

    for region_id, region_data in scoot_region_state.items():

        print(f"\nRegion: {region_id}")
        print(f"  Nodes: {region_data['nodes']}")
        print(f"  Cycle length: {region_data['cycle_length']} s")

    print("\nNodes:")

    for tls in TLS_ORDER:

        print(
            f"  {tls}: "
            f"region={scoot_node_state[tls]['region']}, "
            f"neighbors={SCOOT_NODES[tls]['neighbors']}, "
            f"cycle={scoot_node_state[tls]['cycle_length']}, "
            f"offset={scoot_node_state[tls]['offset']}"
        )

    print("\nDirected SCOOT links:")

    for link_id, link_data in scoot_links.items():

        print(
            f"  {link_id}: "
            f"{link_data['upstream_node']} -> "
            f"{link_data['downstream_node']}"
        )

    for tls, node_data in SCOOT_NODES.items():

        for neighbor in node_data["neighbors"]:

            if neighbor not in TLS_ORDER:
                raise ValueError(
                    f"Invalid SCOOT neighbor: {tls} -> {neighbor}"
                )
            
    for upstream_node, downstream_node in SCOOT_CONNECTIONS:

        if upstream_node not in TLS_ORDER:
            raise ValueError(
                f"Invalid upstream SCOOT node: {upstream_node}"
            )

        if downstream_node not in TLS_ORDER:
            raise ValueError(
                f"Invalid downstream SCOOT node: {downstream_node}"
            )

    print("\n===== END SCOOT NETWORK CHECK =====\n")


def validate_scoot_detectors():

    print("\n===== SCOOT DETECTOR CHECK =====")

    for tls in TLS_ORDER:

        detector_ids = scoot_node_state[tls]["detectors"]

        print(f"\n{tls}: {len(detector_ids)} detectors")

        for detector_id in detector_ids:

            detector = scoot_detectors[detector_id]

            print(
                f"  {detector['lane_id']} | "
                f"edge={detector['edge_id']} | "
                f"lane_length={detector['lane_length']:.1f} m | "
                f"detector={detector['position']:.1f} m"
            )

    print("\n===== END SCOOT DETECTOR CHECK =====\n")

# -----------------------
# FORCE MANUAL TLS CONTROL
# -----------------------
for tls in TLS_ORDER:
    traci.trafficlight.setProgram(tls, "0")
    traci.trafficlight.setPhaseDuration(tls, 999999)


# -----------------------
# SCOOT VIRTUAL DETECTORS
# -----------------------
scoot_detectors = {}
previous_vehicle_positions = {}

for tls in TLS_ORDER:
    scoot_node_state[tls]["detectors"] = []

def build_scoot_detectors():

    for tls in TLS_ORDER:

        lanes = traci.trafficlight.getControlledLanes(tls)

        # Remove duplicate lanes while preserving order
        lanes = list(dict.fromkeys(lanes))

        for lane_id in lanes:

            lane_length = traci.lane.getLength(lane_id)
            edge_id = traci.lane.getEdgeID(lane_id)

            detector_id = f"{tls}:{lane_id}"

            scoot_detectors[detector_id] = {
                "tls": tls,
                "lane_id": lane_id,
                "edge_id": edge_id,
                "lane_length": lane_length,

                "position": min(DETECTOR_POSITION, lane_length),

                "zone_start": min(DETECTOR_ZONE_START, lane_length),
                "zone_end": min(DETECTOR_ZONE_END, lane_length),

                # Current measurements
                "flow_this_step": 0,
                "occupancy_this_step": 0,

                # Historical measurements
                "flow_history": [],
                "occupancy_history": [],

                # Totals for debugging
                "total_flow": 0,
                "occupied_steps": 0
            }

            scoot_node_state[tls]["detectors"].append(detector_id)

def update_scoot_detectors():

    global previous_vehicle_positions

    current_vehicle_positions = {}

    for detector_id, detector in scoot_detectors.items():

        lane_id = detector["lane_id"]
        detector_position = detector["position"]

        zone_start = detector["zone_start"]
        zone_end = detector["zone_end"]

        vehicle_ids = traci.lane.getLastStepVehicleIDs(lane_id)

        flow_count = 0
        vehicles_in_zone = 0

        for veh in vehicle_ids:

            position = traci.vehicle.getLanePosition(veh)

            current_vehicle_positions[veh] = (
                lane_id,
                position
            )

            # ----------------------------------------------
            # FLOW DETECTION
            # ----------------------------------------------

            if veh in previous_vehicle_positions:

                previous_lane, previous_position = (
                    previous_vehicle_positions[veh]
                )

                if (
                    previous_lane == lane_id
                    and previous_position < detector_position
                    and position >= detector_position
                ):
                    flow_count += 1

            # ----------------------------------------------
            # OCCUPANCY DETECTION
            # ----------------------------------------------

            if zone_start <= position <= zone_end:
                vehicles_in_zone += 1

        occupancy = 1 if vehicles_in_zone > 0 else 0

        detector["flow_this_step"] = flow_count
        detector["occupancy_this_step"] = occupancy

        detector["flow_history"].append(flow_count)
        detector["occupancy_history"].append(occupancy)

        detector["total_flow"] += flow_count
        detector["occupied_steps"] += occupancy

    previous_vehicle_positions = current_vehicle_positions

build_scoot_detectors()

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

# Initialize 4D queue_lengths: TLS x Side x Lane x Time
queue_lengths = [[ [ [] for _ in range(NUM_LANES) ] for _ in range(NUM_SIDES) ] for _ in range(NUM_TLS)]
regular_cars = [[ [ [] for _ in range(NUM_LANES) ] for _ in range(NUM_SIDES) ] for _ in range(NUM_TLS)]
tIndex = []

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

        update_scoot_detectors()


# -----------------------
# SIMULATION LOOP
# -----------------------
sim_module = [0] * len(tIndex)  # Track which module each TLS is in

validate_scoot_network()
validate_scoot_detectors()

while traci.simulation.getTime() < END_TIME:

    simStep()

    # ====================================================
    # SCOOT CONTROL LOGIC

    for tls in TLS_REG:
        if sim_module[tIndex.index(tls)] >= 0 and sim_module[tIndex.index(tls)] < ((cycle_length / 2) - 5):
            traci.trafficlight.setRedYellowGreenState(tls, "GGgrrrGGgrrr")
            sim_module[tIndex.index(tls)] += 1

        elif sim_module[tIndex.index(tls)] >= ((cycle_length / 2) - 5) and sim_module[tIndex.index(tls)] < ((cycle_length / 2) - 1):
            traci.trafficlight.setRedYellowGreenState(tls, "yyyrrryyyrrr")
            sim_module[tIndex.index(tls)] += 1

        elif sim_module[tIndex.index(tls)] >= ((cycle_length / 2) - 1) and sim_module[tIndex.index(tls)] < cycle_length / 2:
            traci.trafficlight.setRedYellowGreenState(tls, "rrrrrrrrrrrr")
            sim_module[tIndex.index(tls)] += 1

        elif sim_module[tIndex.index(tls)] >= (cycle_length / 2) and sim_module[tIndex.index(tls)] < (cycle_length - 5):
            traci.trafficlight.setRedYellowGreenState(tls, "rrrGGgrrrGGg")
            sim_module[tIndex.index(tls)] += 1
                
        elif sim_module[tIndex.index(tls)] >= (cycle_length - 5) and sim_module[tIndex.index(tls)] < (cycle_length - 1):
            traci.trafficlight.setRedYellowGreenState(tls, "rrryyyrrryyy")
            sim_module[tIndex.index(tls)] += 1

        elif sim_module[tIndex.index(tls)] >= (cycle_length - 1) and sim_module[tIndex.index(tls)] < cycle_length:
            traci.trafficlight.setRedYellowGreenState(tls, "rrrrrrrrrrrr")
            sim_module[tIndex.index(tls)] = 0

    for tls in TLS_INVERT:        
        if sim_module[tIndex.index(tls)] >= 0 and sim_module[tIndex.index(tls)] < (cycle_length / 2) - 5:
            traci.trafficlight.setRedYellowGreenState(tls, "rrrGGgrrrGGg")
            sim_module[tIndex.index(tls)] += 1
                
        elif sim_module[tIndex.index(tls)] >= (cycle_length / 2) - 5 and sim_module[tIndex.index(tls)] < (cycle_length / 2) - 1:
            traci.trafficlight.setRedYellowGreenState(tls, "rrryyyrrryyy")
            sim_module[tIndex.index(tls)] += 1

        elif sim_module[tIndex.index(tls)] >= (cycle_length / 2) - 1 and sim_module[tIndex.index(tls)] < cycle_length / 2:
            traci.trafficlight.setRedYellowGreenState(tls, "rrrrrrrrrrrr")
            sim_module[tIndex.index(tls)] += 1

        elif sim_module[tIndex.index(tls)] >= cycle_length / 2 and sim_module[tIndex.index(tls)] < (cycle_length - 5):
            traci.trafficlight.setRedYellowGreenState(tls, "GGgrrrGGgrrr")
            sim_module[tIndex.index(tls)] += 1

        elif sim_module[tIndex.index(tls)] >= (cycle_length - 5) and sim_module[tIndex.index(tls)] < cycle_length - 1:
            traci.trafficlight.setRedYellowGreenState(tls, "yyyrrryyyrrr")
            sim_module[tIndex.index(tls)] += 1

        elif sim_module[tIndex.index(tls)] >= (cycle_length - 1) and sim_module[tIndex.index(tls)] < cycle_length:
            traci.trafficlight.setRedYellowGreenState(tls, "rrrrrrrrrrrr")
            sim_module[tIndex.index(tls)] = 0
    
    # ====================================================

def print_scoot_detector_summary():

    print("\n===== SCOOT DETECTOR SUMMARY =====")

    for tls in TLS_ORDER:

        detector_ids = scoot_node_state[tls]["detectors"]

        total_flow = sum(
            scoot_detectors[detector_id]["total_flow"]
            for detector_id in detector_ids
        )

        total_occupied_steps = sum(
            scoot_detectors[detector_id]["occupied_steps"]
            for detector_id in detector_ids
        )

        print(
            f"{tls}: "
            f"detected vehicles={total_flow}, "
            f"occupied detector-steps={total_occupied_steps}"
        )

    print("\nDetector details:")

    for detector_id, detector in scoot_detectors.items():

        samples = len(detector["occupancy_history"])

        if samples > 0:
            occupancy_percent = (
                detector["occupied_steps"]
                / samples
                * 100
            )
        else:
            occupancy_percent = 0.0

        print(
            f"  {detector_id}: "
            f"flow={detector['total_flow']}, "
            f"occupancy={occupancy_percent:.1f}%"
        )

    print("\n===== END SCOOT DETECTOR SUMMARY =====\n")


print_scoot_detector_summary()
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
print("\nSCOOT")
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