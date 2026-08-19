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

# =========================
# Traffic model settings
# -------------------------
SATURATION_FLOW_PER_LANE = 0.5                                     # veh/s/lane
SPLIT_CHANGE = 2       
OFFSET_CHANGE = 4
TOTAL_EFFECTIVE_GREEN = cycle_length - 10                          # seconds

MIN_EFFECTIVE_GREEN = 20                                           # temporary safety bound
MAX_EFFECTIVE_GREEN = TOTAL_EFFECTIVE_GREEN - MIN_EFFECTIVE_GREEN  # seconds 
MIN_SPLIT_IMPROVEMENT = 0.005                                      # don't change split unless saturation is improved by this much

STOP_PENALTY = 20.0
PLATOON_DISPERSION_ALPHA = 0.35
PLATOON_TRAVEL_TIME_FACTOR = 0.80

DISPERSION_WARMUP_CYCLES = 5
OFFSET_QUEUE_WARMUP_CYCLES = 5

# ==========================================================
# SCOOT REGIONAL CYCLE OPTIMIZER SETTINGS
# ==========================================================

IDEAL_SATURATION = 0.90

CYCLE_CHANGE = 4

MIN_REGION_CYCLE = 60
MAX_REGION_CYCLE = 180

CYCLE_OPTIMIZER_INTERVAL = 300
# =========================

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
        "minimum_practical_cycle": cycle_length,
        "offset": 0,

        # Offset optimizer state
        "target_offset": 0,
        "last_offset_decision": "AS_DUE",

        # SCOOT split state
        "stage1_green": 55,
        "stage2_green": 55,

        "last_split_decision": "AS_DUE"
    }

scoot_region_state = {}

for region_id, nodes in SCOOT_REGIONS.items():
    scoot_region_state[region_id] = {
        "nodes": nodes,
        "cycle_length": cycle_length,

        "target_cycle_length": cycle_length,
        "critical_node": None
    }

def normalize_offset(offset):
    normalized = offset % cycle_length
    if normalized > cycle_length / 2:
        normalized -= cycle_length

    return normalized

def get_offset_cycle_second(cycle_second, offset):
    return (cycle_second - offset) % cycle_length

def get_node_max_saturation(tls):

    node_saturations = []

    for approach in (
        scoot_approaches.values()
    ):

        if approach["tls"] == tls:

            node_saturations.append(
                approach[
                    "degree_of_saturation"
                ]
            )

    if not node_saturations:
        return 0.0

    return max(
        node_saturations
    )

def update_node_minimum_practical_cycle(
    tls
):

    max_saturation = (
        get_node_max_saturation(
            tls
        )
    )

    current_mpcy = (
        scoot_node_state[tls][
            "minimum_practical_cycle"
        ]
    )

    if (
        max_saturation
        > IDEAL_SATURATION
    ):

        new_mpcy = (
            current_mpcy
            + CYCLE_CHANGE
        )

    else:

        new_mpcy = (
            current_mpcy
            - CYCLE_CHANGE
        )

    new_mpcy = max(
        MIN_REGION_CYCLE,
        min(
            MAX_REGION_CYCLE,
            new_mpcy
        )
    )

    scoot_node_state[tls][
        "minimum_practical_cycle"
    ] = new_mpcy

    return (
        new_mpcy,
        max_saturation
    )    

def update_cycle_dependent_settings():
    global TOTAL_EFFECTIVE_GREEN
    global MAX_EFFECTIVE_GREEN

    TOTAL_EFFECTIVE_GREEN = cycle_length - 10
    MAX_EFFECTIVE_GREEN = TOTAL_EFFECTIVE_GREEN - MIN_EFFECTIVE_GREEN

def reset_cyclic_profiles_for_new_cycle():
    for approach in scoot_approaches.values():
        approach["flow_sum"] = [0.0] * cycle_length
        approach["occupancy_sum"] = [0.0] * cycle_length
        approach["samples"] = [0] * cycle_length
        approach["flow_profile"] = [0.0] * cycle_length

        approach["occupancy_profile"] = [0.0] * cycle_length
        approach["arrival_profile"] = [0.0] * cycle_length
        approach["dispersed_arrival_profile"] = [0.0] * cycle_length
        approach["queue_profile"] = [0.0] * cycle_length


def rescale_node_splits_for_cycle(tls, old_effective_green):
    old_stage1 = scoot_node_state[tls]["stage1_green"]

    if old_effective_green > 0:
        stage1_ratio = old_stage1 / old_effective_green
    else:
        stage1_ratio = 0.5

    new_stage1 = int(round(stage1_ratio * TOTAL_EFFECTIVE_GREEN))

    # Enforce min and max green
    new_stage1 = max(
        MIN_EFFECTIVE_GREEN,
        min(
            MAX_EFFECTIVE_GREEN,
            new_stage1
        )
    )

    new_stage2 = TOTAL_EFFECTIVE_GREEN - new_stage1
    scoot_node_state[tls]["stage1_green"] = new_stage1
    scoot_node_state[tls]["stage2_green"] = new_stage2


def find_critical_node(
    region_id
):

    nodes = (
        scoot_region_state[
            region_id
        ]["nodes"]
    )

    critical_node = max(
        nodes,
        key=lambda tls: (
            scoot_node_state[tls][
                "minimum_practical_cycle"
            ],
            get_node_max_saturation(
                tls
            )
        )
    )

    return critical_node

def optimize_region_cycle(
    region_id
):

    node_results = {}

    nodes = (
        scoot_region_state[
            region_id
        ]["nodes"]
    )

    for tls in nodes:

        (
            new_mpcy,
            max_saturation

        ) = update_node_minimum_practical_cycle(
            tls
        )

        node_results[tls] = {
            "mpcy": new_mpcy,
            "max_saturation":
                max_saturation
        }
    
    critical_node = (
        find_critical_node(
            region_id
        )
    )

    critical_mpcy = (
        scoot_node_state[
            critical_node
        ][
            "minimum_practical_cycle"
        ]
    )

    current_target = (
        scoot_region_state[
            region_id
        ][
            "target_cycle_length"
        ]
    )

    if (
        critical_mpcy
        > current_target
    ):

        new_target = min(
            current_target
            + CYCLE_CHANGE,
            critical_mpcy
        )

        decision = "INCREASE"

    elif (
        critical_mpcy
        < current_target
    ):

        new_target = max(
            current_target
            - CYCLE_CHANGE,
            critical_mpcy
        )

        decision = "DECREASE"

    else:

        new_target = (
            current_target
        )

        decision = "AS_DUE"

    new_target = max(
        MIN_REGION_CYCLE,
        min(
            MAX_REGION_CYCLE,
            new_target
        )
    )

    scoot_region_state[
        region_id
    ][
        "target_cycle_length"
    ] = new_target

    scoot_region_state[
        region_id
    ][
        "critical_node"
    ] = critical_node

    return decision, new_target, critical_node, node_results



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

def validate_scoot_approaches():

    print("\n===== SCOOT APPROACH CHECK =====")

    for approach_id, approach in scoot_approaches.items():

        print(
            f"{approach_id}: "
            f"TLS={approach['tls']}, "
            f"edge={approach['edge_id']}, "
            f"detectors={len(approach['detectors'])}"
        )

    print(
        f"\nTotal SCOOT approaches: "
        f"{len(scoot_approaches)}"
    )

    print("\n===== END SCOOT APPROACH CHECK =====\n")

def validate_split_timings():

    for tls in TLS_ORDER:

        stage1_green = (
            scoot_node_state[tls][
                "stage1_green"
            ]
        )

        stage2_green = (
            scoot_node_state[tls][
                "stage2_green"
            ]
        )

        # ------------------------------------------
        # Minimum green
        # ------------------------------------------

        if (
            stage1_green
            < MIN_EFFECTIVE_GREEN
        ):
            raise ValueError(
                f"{tls}: stage 1 green "
                f"below minimum"
            )

        if (
            stage2_green
            < MIN_EFFECTIVE_GREEN
        ):
            raise ValueError(
                f"{tls}: stage 2 green "
                f"below minimum"
            )

        # ------------------------------------------
        # Maximum green
        # ------------------------------------------

        if (
            stage1_green
            > MAX_EFFECTIVE_GREEN
        ):
            raise ValueError(
                f"{tls}: stage 1 green "
                f"above maximum"
            )

        if (
            stage2_green
            > MAX_EFFECTIVE_GREEN
        ):
            raise ValueError(
                f"{tls}: stage 2 green "
                f"above maximum"
            )

        # ------------------------------------------
        # Total effective green
        # ------------------------------------------

        if (
            stage1_green
            + stage2_green
            != TOTAL_EFFECTIVE_GREEN
        ):

            raise ValueError(
                f"{tls}: invalid total "
                f"effective green"
            )

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
scoot_approaches = {}

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

def build_scoot_approaches():

    for detector_id, detector in scoot_detectors.items():

        tls = detector["tls"]
        edge_id = detector["edge_id"]

        approach_id = f"{edge_id}->{tls}"

        if approach_id not in scoot_approaches:

            scoot_approaches[approach_id] = {
                "tls": tls,
                "edge_id": edge_id,
                "detectors": [],

                # Running sums for each second of the cycle
                "flow_sum": [0.0] * cycle_length,
                "occupancy_sum": [0.0] * cycle_length,

                # Number of observations made at each cycle second
                "samples": [0] * cycle_length,

                # Current cyclic flow profiles
                "flow_profile": [0.0] * cycle_length,
                "occupancy_profile": [0.0] * cycle_length,

                # Traffic predicted at stop line
                "arrival_profile": [0.0] * cycle_length,
                "dispersed_arrival_profile": [0.0] * cycle_length,
                "dispersion_lag_steps": 0,
                "dispersion_smoothing_factor": 0.0,

                # Predicted queue at stop line
                "queue_profile": [0.0] * cycle_length,

                # Degree of saturation information
                "demand_per_cycle": 0.0,
                "effective_green": 0.0,
                "capacity_per_cycle": 0.0,
                "degree_of_saturation": 0.0,

                # SCOOT performance measures
                "predicted_delay": 0.0,
                "predicted_stops": 0.0,
                "performance_index": 0.0,
            }

        scoot_approaches[approach_id]["detectors"].append(
            detector_id
        )

    # ======================================================
    # CALCULATE APPROACH GEOMETRY
    # ======================================================

    for approach_id, approach in scoot_approaches.items():

        detector_ids = approach["detectors"]

        lane_lengths = []
        lane_speeds = []

        for detector_id in detector_ids:

            detector = scoot_detectors[detector_id]

            lane_id = detector["lane_id"]

            lane_lengths.append(
                detector["lane_length"]
            )

            lane_speeds.append(
                traci.lane.getMaxSpeed(lane_id)
            )
        
        num_lanes = len(detector_ids)
        approach["num_lanes"] = num_lanes


        average_lane_length = (
            sum(lane_lengths)
            / len(lane_lengths)
        )

        distance_to_stopline = (
            average_lane_length
            - DETECTOR_POSITION
        )

        distance_to_stopline = max(
            0.0,
            distance_to_stopline
        )

        approach["distance_to_stopline"] = (
            distance_to_stopline
        )

        
        average_speed = (
            sum(lane_speeds)
            / len(lane_speeds)
        )

        approach["cruise_speed"] = (
            average_speed
        )

        if average_speed > 0:
            travel_time = distance_to_stopline / average_speed
        else:
            travel_time = 0.0


        travel_time_steps = max(
            0,
            int(round(travel_time))
        )

        approach["travel_time"] = (
            travel_time
        )

        approach["travel_time_steps"] = (
            travel_time_steps
        )

        first_detector_id = (
            detector_ids[0]
        )

        first_lane_id = (
            scoot_detectors[
                first_detector_id
            ]["lane_id"]
        )

        controlled_lanes = (
            traci.trafficlight
            .getControlledLanes(
                approach["tls"]
            )
        )

        controlled_lanes = list(
            dict.fromkeys(
                controlled_lanes
            )
        )

        first_lane_position = (
            controlled_lanes.index(
                first_lane_id
            )
        )

        lanes_per_side = (
            len(controlled_lanes)
            // 4
        )

        side_index = (
            first_lane_position
            // lanes_per_side
        )

        approach["side_index"] = side_index
        approach["is_internal_link"] = False
        approach["upstream_node"] = None

        for (upstream_node, downstream_node) in SCOOT_CONNECTIONS:
            expected_edge = (
                f"{upstream_node}"
                f"{downstream_node}"
            )

            if (approach["edge_id"] == expected_edge and approach["tls"] == downstream_node):
                approach["is_internal_link"] = True
                approach["upstream_node"] = upstream_node
                break


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

def update_cyclic_flow_profiles():

    current_time = int(traci.simulation.getTime())

    cycle_position = (
        (current_time - 1)
        % cycle_length
    )

    for approach_id, approach in scoot_approaches.items():

        detector_ids = approach["detectors"]

        total_flow = 0
        occupied_detectors = 0

        for detector_id in detector_ids:

            detector = scoot_detectors[detector_id]

            total_flow += detector["flow_this_step"]

            occupied_detectors += (
                detector["occupancy_this_step"]
            )

        if len(detector_ids) > 0:

            occupancy_fraction = (
                occupied_detectors
                / len(detector_ids)
            )

        else:

            occupancy_fraction = 0.0

        approach["flow_sum"][cycle_position] += (
            total_flow
        )

        approach["occupancy_sum"][cycle_position] += (
            occupancy_fraction
        )

        approach["samples"][cycle_position] += 1

        samples = approach["samples"][cycle_position]

        approach["flow_profile"][cycle_position] = (
            approach["flow_sum"][cycle_position]
            / samples
        )

        approach["occupancy_profile"][cycle_position] = (
            approach["occupancy_sum"][cycle_position]
            / samples
        )

def disperse_flow_profile(flow_profile, average_travel_time):
    alpha = PLATOON_DISPERSION_ALPHA
    beta = PLATOON_TRAVEL_TIME_FACTOR

    lag_steps = max(1, int(round(beta * average_travel_time)))
    smoothing_factor = 1.0 / (1.0 + alpha * beta * average_travel_time)
    repeated_profile = flow_profile * DISPERSION_WARMUP_CYCLES
    dispersed = [0.0] * len(repeated_profile)

    for t in range(len(repeated_profile)):
        source_index = t - lag_steps
        if source_index >= 0:
            upstream_flow = repeated_profile[source_index]
        else:
            upstream_flow = 0.0

        if t > 0:
            previous_downstream_flow = dispersed[t-1]
        else:
            previous_downstream_flow = 0.0

        dispersed[t] = smoothing_factor * upstream_flow + (1.0 - smoothing_factor) * previous_downstream_flow
    
    final_cycle_start = len(repeated_profile) - cycle_length
    final_profile = dispersed[final_cycle_start:]

    return final_profile, lag_steps, smoothing_factor

def update_stopline_arrival_profiles():

    for approach_id, approach in (
        scoot_approaches.items()
    ):

        flow_profile = (
            approach["flow_profile"]
        )

        average_travel_time = (
            approach["travel_time"]
        )

        (
            dispersed_profile,
            lag_steps,
            smoothing_factor

        ) = disperse_flow_profile(
            flow_profile,
            average_travel_time
        )

        approach[
            "dispersed_arrival_profile"
        ] = dispersed_profile

        approach[
            "arrival_profile"
        ] = dispersed_profile

        approach[
            "dispersion_lag_steps"
        ] = lag_steps

        approach[
            "dispersion_smoothing_factor"
        ] = smoothing_factor


def is_approach_green(tls, side_index, cycle_second):
    stage1_green = scoot_node_state[tls]["stage1_green"]
    stage2_start = stage1_green + 5

    if tls in TLS_REG:
        if side_index in [0, 2]:
            return cycle_second < stage1_green

        elif side_index in [1, 3]:
            return cycle_second >= stage2_start and cycle_second < cycle_length - 5

    elif tls in TLS_INVERT:
        if side_index in [1, 3]:
            return cycle_second < stage1_green
    
        elif side_index in [0, 2]:
            return cycle_second >= stage2_start and cycle_second < cycle_length - 5

    return False

def is_approach_green_at_offset(
    tls,
    side_index,
    cycle_second,
    offset
):

    local_second = (
        get_offset_cycle_second(
            cycle_second,
            offset
        )
    )

    stage1_green = (
        scoot_node_state[tls][
            "stage1_green"
        ]
    )

    stage2_start = (
        stage1_green + 5
    )

    if tls in TLS_REG:

        if side_index in [0, 2]:

            return (
                local_second
                < stage1_green
            )

        elif side_index in [1, 3]:

            return (
                local_second
                >= stage2_start
                and
                local_second
                < cycle_length - 5
            )

    elif tls in TLS_INVERT:

        if side_index in [1, 3]:

            return (
                local_second
                < stage1_green
            )

        elif side_index in [0, 2]:

            return (
                local_second
                >= stage2_start
                and
                local_second
                < cycle_length - 5
            )

    return False
def calculate_queue_for_offset(
    approach,
    candidate_offset
):

    tls = approach["tls"]
    side_index = approach["side_index"]

    arrivals = approach[
        "arrival_profile"
    ]

    num_lanes = approach[
        "num_lanes"
    ]

    max_discharge = (
        SATURATION_FLOW_PER_LANE
        * num_lanes
    )

    # Repeat arrivals so the queue can settle
    repeated_arrivals = (
        arrivals
        * OFFSET_QUEUE_WARMUP_CYCLES
    )

    repeated_queue = (
        [0.0]
        * len(repeated_arrivals)
    )

    queue = 0.0

    for t in range(
        len(repeated_arrivals)
    ):

        cycle_second = (
            t % cycle_length
        )

        queue += (
            repeated_arrivals[t]
        )

        green = (
            is_approach_green_at_offset(
                tls,
                side_index,
                cycle_second,
                candidate_offset
            )
        )

        if green:

            discharge = min(
                queue,
                max_discharge
            )

            queue -= discharge

        repeated_queue[t] = queue

    # Keep only the final settled cycle
    final_cycle_start = (
        len(repeated_queue)
        - cycle_length
    )

    queue_profile = (
        repeated_queue[
            final_cycle_start:
        ]
    )

    return queue_profile

def calculate_stops_for_offset(
    approach,
    queue_profile,
    candidate_offset
):

    tls = approach["tls"]

    side_index = (
        approach["side_index"]
    )

    arrivals = (
        approach["arrival_profile"]
    )

    predicted_stops = 0.0

    for cycle_second in range(
        cycle_length
    ):

        arriving_vehicles = (
            arrivals[
                cycle_second
            ]
        )

        green = (
            is_approach_green_at_offset(
                tls,
                side_index,
                cycle_second,
                candidate_offset
            )
        )

        if not green:

            predicted_stops += (
                arriving_vehicles
            )

        elif (
            queue_profile[
                (cycle_second - 1)
                % cycle_length
            ] > 0
        ):

            predicted_stops += (
                arriving_vehicles
            )

    return predicted_stops

def calculate_pi_for_offset(
    approach,
    candidate_offset
):

    queue_profile = (
        calculate_queue_for_offset(
            approach,
            candidate_offset
        )
    )

    predicted_delay = sum(
        queue_profile
    )

    predicted_stops = (
        calculate_stops_for_offset(
            approach,
            queue_profile,
            candidate_offset
        )
    )

    performance_index = (
        predicted_delay
        + STOP_PENALTY
        * predicted_stops
    )

    return performance_index

def evaluate_offset_candidate(
    tls,
    candidate_offset
):

    total_pi = 0.0

    for approach in (
        scoot_approaches.values()
    ):

        if approach["tls"] != tls:
            continue

        approach_pi = (
            calculate_pi_for_offset(
                approach,
                candidate_offset
            )
        )

        total_pi += approach_pi

    return total_pi

def optimize_offset(tls):

    current_offset = (
        scoot_node_state[tls][
            "target_offset"
        ]
    )

    candidates = {
        "EARLIER":
            normalize_offset(
                current_offset
                - OFFSET_CHANGE
            ),

        "AS_DUE":
            normalize_offset(
                current_offset
            ),

        "LATER":
            normalize_offset(
                current_offset
                + OFFSET_CHANGE
            )
    }

    candidate_scores = {}

    for (
        decision,
        candidate_offset
    ) in candidates.items():

        score = (
            evaluate_offset_candidate(
                tls,
                candidate_offset
            )
        )

        candidate_scores[
            decision
        ] = score

    decision_priority = {
        "AS_DUE": 0,
        "EARLIER": 1,
        "LATER": 2
    }

    best_decision = min(
        candidate_scores,
        key=lambda decision: (
            candidate_scores[
                decision
            ],
            decision_priority[
                decision
            ]
        )
    )

    best_offset = (
        candidates[
            best_decision
        ]
    )

    scoot_node_state[tls][
        "target_offset"
    ] = best_offset

    scoot_node_state[tls][
        "last_offset_decision"
    ] = best_decision

    return (
        best_decision,
        candidate_scores,
        best_offset
    )

def is_stage1_approach(tls, side_index):
    # Normal intersections:
    # first stage serves sides 0 and 2
    if tls in TLS_REG:
        return side_index in [0, 2]

    # Inverted B1:
    # first stage serves sides 1 and 3
    elif tls in TLS_INVERT:
        return side_index in [1, 3]

    return False

def calculate_degree_of_saturation(approach, effective_green):
    # ----------------------------------------------
    # Demand
    # ----------------------------------------------

    demand_per_cycle = sum(
        approach["arrival_profile"]
    )

    # ----------------------------------------------
    # Saturation capacity while green
    # ----------------------------------------------

    saturation_capacity_per_second = (
        SATURATION_FLOW_PER_LANE
        * approach["num_lanes"]
    )

    # ----------------------------------------------
    # Total capacity available during this cycle
    # ----------------------------------------------

    capacity_per_cycle = (
        saturation_capacity_per_second
        * effective_green
    )

    # ----------------------------------------------
    # Degree of saturation
    # ----------------------------------------------

    if capacity_per_cycle > 0:

        degree_of_saturation = (
            demand_per_cycle
            / capacity_per_cycle
        )

    else:

        if demand_per_cycle > 0:
            degree_of_saturation = float("inf")
        else:
            degree_of_saturation = 0.0

    return (
        degree_of_saturation,
        demand_per_cycle,
        capacity_per_cycle
    )

def get_current_effective_green(tls, side_index):
    green_seconds = 0

    for cycle_second in range(cycle_length):
        if is_approach_green(tls, side_index, cycle_second):
            green_seconds += 1

    return green_seconds


def update_degrees_of_saturation():
    for approach_id, approach in scoot_approaches.items():
        tls = approach["tls"]
        side_index = approach["side_index"]

        effective_green = (
            get_current_effective_green(tls, side_index)
        )

        (degree_of_saturation, demand_per_cycle, capacity_per_cycle 
        ) = calculate_degree_of_saturation(approach, effective_green)

        approach["effective_green"] = effective_green
        approach["demand_per_cycle"] = demand_per_cycle
        approach["capacity_per_cycle"] = capacity_per_cycle
        approach["degree_of_saturation"] = degree_of_saturation


def update_predicted_queue_profiles():

    for approach_id, approach in (
        scoot_approaches.items()
    ):

        tls = approach["tls"]
        side_index = approach["side_index"]

        arrivals = (
            approach["arrival_profile"]
        )

        num_lanes = approach["num_lanes"]

        max_discharge = (
            SATURATION_FLOW_PER_LANE
            * num_lanes
        )

        queue_profile = (
            [0.0] * cycle_length
        )

        queue = 0.0

        for cycle_second in range(cycle_length):

            # Vehicles arrive
            queue += arrivals[
                cycle_second
            ]

            green = is_approach_green(
                tls,
                side_index,
                cycle_second
            )

            if green:

                discharge = min(
                    queue,
                    max_discharge
                )

                queue -= discharge
        
            queue_profile[
                cycle_second
            ] = queue

        approach["queue_profile"] = (
            queue_profile
        )

def calculate_predicted_stops(approach):
    tls = approach["tls"]
    side_index = approach["side_index"]
    arrivals = approach["arrival_profile"]
    queue_profile = approach["queue_profile"]

    predicted_stops = 0.0

    for cycle_second in range(cycle_length):
        arriving_vehicles = arrivals[cycle_second]
        green = is_approach_green(tls, side_index, cycle_second)

        if not green:
            predicted_stops += arriving_vehicles

        # ------------------------------------------
        # Vehicles arriving during green can
        # still stop if a queue already exists
        # ------------------------------------------

        elif (cycle_second > 0 and queue_profile[cycle_second - 1] > 0):
            predicted_stops += arriving_vehicles

    return predicted_stops

def calculate_performance_index(approach):
    predicted_delay = sum(approach["queue_profile"])
    predicted_stops = calculate_predicted_stops(approach)
    performance_index = predicted_delay + STOP_PENALTY * predicted_stops

    return performance_index, predicted_delay, predicted_stops

def update_performance_indices():
    for approach_id, approach in scoot_approaches.items():
        pI, pD, pS = calculate_performance_index(approach)
        approach["predicted_delay"] = pD
        approach["predicted_stops"] = pS
        approach["performance_index"] = pI


def evaluate_split_candidate(tls, stage1_green):
    stage2_green = TOTAL_EFFECTIVE_GREEN - stage1_green
    worst_saturation = 0.0

    for approach in scoot_approaches.values():

        if approach["tls"] != tls:
            continue

        side_index = approach["side_index"]

        if is_stage1_approach(tls, side_index):
            effective_green = stage1_green
        else:
            effective_green = stage2_green


        (
            degree_of_saturation,
            _,
            _
        ) = calculate_degree_of_saturation(
            approach,
            effective_green
        )

        worst_saturation = max(
            worst_saturation,
            degree_of_saturation
        )

    return worst_saturation

def optimize_split(tls):
    current_stage1 = scoot_node_state[tls]["stage1_green"]
    
    candidates = {
        "EARLIER": (
            current_stage1
            - SPLIT_CHANGE
        ),

        "AS_DUE": (
            current_stage1
        ),

        "LATER": (
            current_stage1
            + SPLIT_CHANGE
        )
    }

    valid_candidates = {}

    for decision, candidate_green in candidates.items():
        candidate_stage2 = TOTAL_EFFECTIVE_GREEN - candidate_green
        
        if (candidate_green >= MIN_EFFECTIVE_GREEN
            and
            candidate_green <= MAX_EFFECTIVE_GREEN
            and
            candidate_stage2 >= MIN_EFFECTIVE_GREEN
            and
            candidate_stage2 <= MAX_EFFECTIVE_GREEN
        ):

            valid_candidates[decision] = candidate_green

        candidate_scores = {}

    for decision, candidate_green in valid_candidates.items():
        score = evaluate_split_candidate(tls, candidate_green)
        candidate_scores[decision] = score

    
    decision_priority = {
        "AS_DUE": 0,
        "EARLIER": 1,
        "LATER": 2
    }

    best_decision = min(
        candidate_scores,
        key=lambda decision: (
            candidate_scores[decision],
            decision_priority[decision]
        )
    )

    current_score = candidate_scores["AS_DUE"]
    best_score = candidate_scores[best_decision]
    improvement = current_score - best_score

    if(best_decision != "AS_DUE" and improvement < MIN_SPLIT_IMPROVEMENT):
        best_decision = "AS_DUE"

    best_stage1 = valid_candidates[best_decision]
    best_stage2 = TOTAL_EFFECTIVE_GREEN - best_stage1
    scoot_node_state[tls]["stage1_green"] = best_stage1
    scoot_node_state[tls]["stage2_green"] = best_stage2
    scoot_node_state[tls]["last_split_decision"] = best_decision

    return best_decision, candidate_scores, improvement


build_scoot_detectors()
build_scoot_approaches()

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
        update_cyclic_flow_profiles()

        update_stopline_arrival_profiles()
        update_predicted_queue_profiles()
        update_degrees_of_saturation()
        update_performance_indices()

# -----------------------
# SIMULATION LOOP
# -----------------------
sim_module = [0] * len(tIndex)  # Track which module each TLS is in
split_history = {tls: [] for tls in TLS_ORDER}  # Track split decisions for each TLS
offset_history = {tls: [] for tls in TLS_ORDER}
cycle_history = []

validate_scoot_network()
validate_scoot_detectors()
validate_scoot_approaches()

while traci.simulation.getTime() < END_TIME:

    simStep()
    current_time = int(traci.simulation.getTime())

    # ====================================================
    # SCOOT SPLIT OPTIMIZER
    # ====================================================

    if current_time >= cycle_length:
        for tls in TLS_ORDER:
            tls_index = tIndex.index(tls)

            if sim_module[tls_index] == 0:
                decision, candidate_scores, improvement = optimize_split(tls)
                validate_split_timings()

                split_history[tls].append(
                    {
                        "time": current_time,
                        "decision": decision,
                        "stage1_green":
                            scoot_node_state[tls][
                                "stage1_green"
                            ],
                        "stage2_green":
                            scoot_node_state[tls][
                                "stage2_green"
                            ],
                        "scores":
                            candidate_scores.copy(),
                        "improvement": improvement
                    }
                )
    
    # ====================================================
    # SCOOT OFFSET OPTIMIZER
    # ====================================================

    if (current_time >= 2 * cycle_length and current_time % cycle_length == 1):
        for tls in ["A1", "B0", "B1"]:
            decision, candidate_scores, best_offset = optimize_offset(tls)
            offset_history[tls].append(
                {
                    "time":
                        current_time,

                    "decision":
                        decision,

                    "offset":
                        best_offset,

                    "scores":
                        candidate_scores.copy()
                }
            )
        
    # ====================================================
    # SCOOT REGIONAL CYCLE OPTIMIZER
    # ====================================================

    if (current_time >= CYCLE_OPTIMIZER_INTERVAL and current_time % CYCLE_OPTIMIZER_INTERVAL == 0):
        decision, target_cycle, critical_node, node_results = optimize_region_cycle("R0")
        cycle_history.append(
            {
                "time":
                    current_time,

                "decision":
                    decision,

                "target_cycle":
                    target_cycle,

                "critical_node":
                    critical_node,

                "nodes":
                    node_results
            }
        )

    # ==========================================

    for tls in TLS_REG:
        tls_index = tIndex.index(tls)
        stage1_green = scoot_node_state[tls]["stage1_green"]
        stage2_start = stage1_green + 5
        
        if sim_module[tls_index] >= 0 and sim_module[tls_index] < stage1_green:
            traci.trafficlight.setRedYellowGreenState(tls, "GGgrrrGGgrrr")
            sim_module[tls_index] += 1

        elif sim_module[tls_index] >= stage1_green and sim_module[tls_index] < stage1_green + 4:
            traci.trafficlight.setRedYellowGreenState(tls, "yyyrrryyyrrr")
            sim_module[tls_index] += 1

        elif sim_module[tls_index] >= stage1_green + 4 and sim_module[tls_index] < stage1_green + 5:
            traci.trafficlight.setRedYellowGreenState(tls, "rrrrrrrrrrrr")
            sim_module[tls_index] += 1

        elif sim_module[tls_index] >= stage2_start and sim_module[tls_index] < (cycle_length - 5):
            traci.trafficlight.setRedYellowGreenState(tls, "rrrGGgrrrGGg")
            sim_module[tls_index] += 1
                
        elif sim_module[tls_index] >= (cycle_length - 5) and sim_module[tls_index] < (cycle_length - 1):
            traci.trafficlight.setRedYellowGreenState(tls, "rrryyyrrryyy")
            sim_module[tls_index] += 1

        elif sim_module[tls_index] >= (cycle_length - 1) and sim_module[tls_index] < cycle_length:
            traci.trafficlight.setRedYellowGreenState(tls, "rrrrrrrrrrrr")
            sim_module[tls_index] = 0

    for tls in TLS_INVERT:        
        tls_index = tIndex.index(tls)
        stage1_green = scoot_node_state[tls]["stage1_green"]
        stage2_start = stage1_green + 5
        
        if sim_module[tls_index] >= 0 and sim_module[tls_index] < stage1_green:
            traci.trafficlight.setRedYellowGreenState(tls, "rrrGGgrrrGGg")
            sim_module[tls_index] += 1

        elif sim_module[tls_index] >= stage1_green and sim_module[tls_index] < stage1_green + 4:
            traci.trafficlight.setRedYellowGreenState(tls, "rrryyyrrryyy")
            sim_module[tls_index] += 1

        elif sim_module[tls_index] >= stage1_green + 4 and sim_module[tls_index] < stage1_green + 5:
            traci.trafficlight.setRedYellowGreenState(tls, "rrrrrrrrrrrr")
            sim_module[tls_index] += 1

        elif sim_module[tls_index] >= stage2_start and sim_module[tls_index] < (cycle_length - 5):
            traci.trafficlight.setRedYellowGreenState(tls, "GGgrrrGGgrrr")
            sim_module[tls_index] += 1
                
        elif sim_module[tls_index] >= (cycle_length - 5) and sim_module[tls_index] < (cycle_length - 1):
            traci.trafficlight.setRedYellowGreenState(tls, "yyyrrryyyrrr")
            sim_module[tls_index] += 1

        elif sim_module[tls_index] >= (cycle_length - 1) and sim_module[tls_index] < cycle_length:
            traci.trafficlight.setRedYellowGreenState(tls, "rrrrrrrrrrrr")
            sim_module[tls_index] = 0
    
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

def print_cyclic_flow_profile_summary():

    print("\n===== SCOOT CYCLIC FLOW PROFILE CHECK =====")

    for approach_id, approach in scoot_approaches.items():

        flow_profile = approach["flow_profile"]
        occupancy_profile = approach["occupancy_profile"]

        observed_slots = sum(
            1
            for sample_count in approach["samples"]
            if sample_count > 0
        )

        total_samples = sum(
            approach["samples"]
        )

        peak_flow = max(flow_profile)

        peak_flow_second = flow_profile.index(
            peak_flow
        )

        peak_occupancy = max(
            occupancy_profile
        )

        peak_occupancy_second = (
            occupancy_profile.index(
                peak_occupancy
            )
        )

        print(
            f"\n{approach_id}"
        )

        print(
            f"  observed cycle slots: "
            f"{observed_slots}/{cycle_length}"
        )

        print(
            f"  total slot observations: "
            f"{total_samples}"
        )

        print(
            f"  peak avg flow: "
            f"{peak_flow:.2f} veh/s "
            f"at cycle second "
            f"{peak_flow_second}"
        )

        print(
            f"  peak avg occupancy: "
            f"{peak_occupancy * 100:.1f}% "
            f"at cycle second "
            f"{peak_occupancy_second}"
        )

        print(
            "  first 20 flow slots: "
            + str(
                [
                    round(value, 2)
                    for value
                    in flow_profile[:20]
                ]
            )
        )

        print(
            "  first 20 occupancy slots: "
            + str(
                [
                    round(value, 2)
                    for value
                    in occupancy_profile[:20]
                ]
            )
        )

        
        min_samples = min(
            approach["samples"]
        )

        max_samples = max(
            approach["samples"]
        )

        print(
            f"  samples per cycle slot: "
            f"min={min_samples}, "
            f"max={max_samples}"
        )

        print(
            f"  lanes={approach['num_lanes']}, "
            f"side={approach['side_index']}, "
            f"distance_to_stopline="
            f"{approach['distance_to_stopline']:.1f} m, "
            f"speed="
            f"{approach['cruise_speed']:.1f} m/s, "
            f"travel_time="
            f"{approach['travel_time']:.1f} s "
            f"({approach['travel_time_steps']} steps)"
        )

    print(
        "\n===== END SCOOT CYCLIC FLOW PROFILE CHECK =====\n"
    )

def print_queue_prediction_summary():

    print(
        "\n===== SCOOT QUEUE PREDICTION CHECK ====="
    )

    for approach_id, approach in (
        scoot_approaches.items()
    ):

        arrivals = (
            approach["arrival_profile"]
        )

        queues = (
            approach["queue_profile"]
        )

        peak_arrival = max(arrivals)

        peak_arrival_second = (
            arrivals.index(
                peak_arrival
            )
        )

        max_queue = max(queues)

        max_queue_second = (
            queues.index(
                max_queue
            )
        )

        avg_queue = (
            sum(queues)
            / len(queues)
        )

        print(
            f"\n{approach_id}"
        )

        print(
            f"  travel time: "
            f"{approach['travel_time']:.1f} s"
        )

        print(
            f"  peak predicted arrival: "
            f"{peak_arrival:.2f} veh/s "
            f"at second "
            f"{peak_arrival_second}"
        )

        print(
            f"  max predicted queue: "
            f"{max_queue:.2f} veh "
            f"at second "
            f"{max_queue_second}"
        )

        print(
            f"  avg predicted queue: "
            f"{avg_queue:.2f} veh"
        )

        print(
            "  first 20 queue slots: "
            + str(
                [
                    round(value, 2)
                    for value
                    in queues[:20]
                ]
            )
        )

    print(
        "\n===== END SCOOT QUEUE PREDICTION CHECK =====\n"
    )

def print_degree_of_saturation_summary():

    print(
        "\n===== SCOOT DEGREE OF SATURATION CHECK ====="
    )

    for approach_id, approach in (
        scoot_approaches.items()
    ):

        degree = (
            approach["degree_of_saturation"]
        )

        print(
            f"\n{approach_id}"
        )

        print(
            f"  demand per cycle: "
            f"{approach['demand_per_cycle']:.2f} veh"
        )

        print(
            f"  effective green: "
            f"{approach['effective_green']:.0f} s"
        )

        print(
            f"  capacity per cycle: "
            f"{approach['capacity_per_cycle']:.2f} veh"
        )

        print(
            f"  degree of saturation: "
            f"{degree:.3f} "
            f"({degree * 100:.1f}%)"
        )

    print("\nMaximum saturation by node:")

    for tls in TLS_ORDER:

        node_approaches = [
            approach
            for approach in scoot_approaches.values()
            if approach["tls"] == tls
        ]

        if node_approaches:

            worst_approach = max(
                node_approaches,
                key=lambda approach:
                    approach[
                        "degree_of_saturation"
                    ]
            )

            print(
                f"  {tls}: "
                f"{worst_approach['degree_of_saturation'] * 100:.1f}%"
            )

    print(
        "\n===== END SCOOT DEGREE OF SATURATION CHECK =====\n"
    )

def print_split_optimizer_summary():

    print(
        "\n===== SCOOT SPLIT OPTIMIZER CHECK ====="
    )

    for tls in TLS_ORDER:

        print(f"\n{tls}:")

        history = split_history[tls]

        if not history:

            print(
                "  No split decisions made."
            )
            continue

        for record in history:

            print(
                f"  t={record['time']}: "
                f"{record['decision']} | "
                f"stage1="
                f"{record['stage1_green']} s | "
                f"stage2="
                f"{record['stage2_green']} s"
            )

            scores = record["scores"]

            for decision in [
                "EARLIER",
                "AS_DUE",
                "LATER"
            ]:

                if decision in scores:

                    print(
                        f"    {decision}: "
                        f"max saturation="
                        f"{scores[decision] * 100:.1f}%"
                    )

    print(
        f"    candidate improvement: "
        f"{record['improvement'] * 100:.2f} "
        f"percentage points"
    )

    print(
        "\n===== END SCOOT SPLIT OPTIMIZER CHECK =====\n"
    )

def print_performance_index_summary():

    print(
        "\n===== SCOOT PERFORMANCE INDEX CHECK ====="
    )

    for approach_id, approach in (
        scoot_approaches.items()
    ):

        print(
            f"\n{approach_id}"
        )

        print(
            f"  predicted delay: "
            f"{approach['predicted_delay']:.2f} "
            f"veh-s"
        )

        print(
            f"  predicted stops: "
            f"{approach['predicted_stops']:.2f} veh"
        )

        print(
            f"  performance index: "
            f"{approach['performance_index']:.2f}"
        )

    print(
        "\nTotal Performance Index by node:"
    )

    for tls in TLS_ORDER:

        node_pi = sum(
            approach[
                "performance_index"
            ]
            for approach
            in scoot_approaches.values()
            if approach["tls"] == tls
        )

        print(
            f"  {tls}: "
            f"{node_pi:.2f}"
        )


    network_pi = sum(
        approach[
            "performance_index"
        ]
        for approach
        in scoot_approaches.values()
    )

    print(
        f"\nNetwork Performance Index: "
        f"{network_pi:.2f}"
    )

    print(
        "\n===== END SCOOT PERFORMANCE INDEX CHECK =====\n"
    )

def print_platoon_dispersion_summary():

    print(
        "\n===== SCOOT PLATOON DISPERSION CHECK ====="
    )

    for approach_id, approach in (
        scoot_approaches.items()
    ):

        if not approach[
            "is_internal_link"
        ]:
            continue

        original = (
            approach["flow_profile"]
        )

        dispersed = (
            approach[
                "dispersed_arrival_profile"
            ]
        )

        original_peak = max(original)
        dispersed_peak = max(dispersed)

        original_total = sum(original)
        dispersed_total = sum(dispersed)

        print(
            f"\n{approach_id}"
        )

        print(
            f"  upstream node: "
            f"{approach['upstream_node']}"
        )

        print(
            f"  downstream node: "
            f"{approach['tls']}"
        )

        print(
            f"  travel time: "
            f"{approach['travel_time']:.2f} s"
        )

        print(
            f"  lag steps: "
            f"{approach['dispersion_lag_steps']}"
        )

        print(
            f"  smoothing factor: "
            f"{approach['dispersion_smoothing_factor']:.3f}"
        )

        print(
            f"  original peak: "
            f"{original_peak:.3f}"
        )

        print(
            f"  dispersed peak: "
            f"{dispersed_peak:.3f}"
        )

        print(
            f"  original total flow: "
            f"{original_total:.2f}"
        )

        print(
            f"  dispersed total flow: "
            f"{dispersed_total:.2f}"
        )

        flow_difference = abs(
            original_total
            - dispersed_total
        )

        if flow_difference > 0.5:

            print(
                "  WARNING: large flow "
                "difference after dispersion"
            )

    print(
        "\n===== END SCOOT PLATOON DISPERSION CHECK =====\n"
    )

def print_offset_optimizer_summary():

    print(
        "\n===== SCOOT OFFSET OPTIMIZER CHECK ====="
    )

    print(
        "\nA0: regional reference offset = 0 s"
    )

    for tls in [
        "A1",
        "B0",
        "B1"
    ]:

        print(
            f"\n{tls}:"
        )

        history = (
            offset_history[tls]
        )

        if not history:

            print(
                "  No offset decisions made."
            )

            continue

        for record in history:

            print(
                f"  t={record['time']}: "
                f"{record['decision']} | "
                f"target offset="
                f"{record['offset']} s"
            )

            scores = (
                record["scores"]
            )

            for decision in [
                "EARLIER",
                "AS_DUE",
                "LATER"
            ]:

                print(
                    f"    {decision}: "
                    f"PI="
                    f"{scores[decision]:.2f}"
                )

    print(
        "\n===== END SCOOT OFFSET OPTIMIZER CHECK =====\n"
    )

def print_cycle_optimizer_summary():

    print(
        "\n===== SCOOT REGIONAL CYCLE OPTIMIZER CHECK ====="
    )

    for record in cycle_history:

        print(
            f"\nt={record['time']}: "
            f"{record['decision']} | "
            f"target cycle="
            f"{record['target_cycle']} s | "
            f"critical node="
            f"{record['critical_node']}"
        )

        for (
            tls,
            data
        ) in record[
            "nodes"
        ].items():

            print(
                f"  {tls}: "
                f"max saturation="
                f"{data['max_saturation'] * 100:.1f}% | "
                f"MPCY="
                f"{data['mpcy']} s"
            )

    print(
        "\n===== END SCOOT REGIONAL CYCLE OPTIMIZER CHECK =====\n"
    )

print_scoot_detector_summary()
print_cyclic_flow_profile_summary()
print_queue_prediction_summary()
print_degree_of_saturation_summary()
print_split_optimizer_summary()
print_performance_index_summary()
print_platoon_dispersion_summary()
print_offset_optimizer_summary()
print_cycle_optimizer_summary()

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