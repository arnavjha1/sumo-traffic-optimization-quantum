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


model_ready = True

def apply_target_region_cycle(
    region_id
):

    global cycle_length
    global model_ready

    target_cycle = (
        scoot_region_state[
            region_id
        ][
            "target_cycle_length"
        ]
    )

    if target_cycle == cycle_length:
        return False

    old_cycle = cycle_length

    old_effective_green = (
        TOTAL_EFFECTIVE_GREEN
    )

    # ------------------------------------------
    # Apply new regional cycle
    # ------------------------------------------

    cycle_length = target_cycle

    update_cycle_dependent_settings()

    # ------------------------------------------
    # Update region/node cycle state
    # ------------------------------------------

    scoot_region_state[
        region_id
    ]["cycle_length"] = cycle_length

    for tls in (
        scoot_region_state[
            region_id
        ]["nodes"]
    ):

        scoot_node_state[tls][
            "cycle_length"
        ] = cycle_length

        rescale_node_splits_for_cycle(
            tls,
            old_effective_green
        )

    model_ready = False
    # ------------------------------------------
    # Rebuild cycle-based traffic profiles
    # ------------------------------------------

    reset_cyclic_profiles_for_new_cycle()

    print(
        "\n===== SCOOT CYCLE APPLIED ====="
    )

    print(
        f"Cycle changed: "
        f"{old_cycle} -> "
        f"{cycle_length} s"
    )

    for tls in TLS_ORDER:

        print(
            f"  {tls}: "
            f"stage1="
            f"{scoot_node_state[tls]['stage1_green']} s, "
            f"stage2="
            f"{scoot_node_state[tls]['stage2_green']} s"
        )

    print(
        "===== END SCOOT CYCLE APPLIED =====\n"
    )

    return True

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
        
def validate_integrated_scoot():

    # =====================================================
    # 1. REGIONAL CYCLE CHECK
    # =====================================================

    if not (
        MIN_REGION_CYCLE
        <= cycle_length
        <= MAX_REGION_CYCLE
    ):

        raise ValueError(
            f"Invalid cycle length: "
            f"{cycle_length}"
        )


    # =====================================================
    # 2. REGIONAL CLOCK CHECK
    # =====================================================

    if not (
        0
        <= regional_cycle_second
        < cycle_length
    ):

        raise ValueError(
            f"Invalid regional cycle second: "
            f"{regional_cycle_second}"
        )


    # =====================================================
    # 3. NODE TIMING CHECKS
    # =====================================================

    for tls in TLS_ORDER:

        stage1 = (
            scoot_node_state[tls][
                "stage1_green"
            ]
        )

        stage2 = (
            scoot_node_state[tls][
                "stage2_green"
            ]
        )

        offset = (
            scoot_node_state[tls][
                "offset"
            ]
        )

        # Minimum green
        if (
            stage1 < MIN_EFFECTIVE_GREEN
            or
            stage2 < MIN_EFFECTIVE_GREEN
        ):

            raise ValueError(
                f"{tls}: green below minimum"
            )

        # Total green must match active cycle
        if (
            stage1
            + stage2
            != TOTAL_EFFECTIVE_GREEN
        ):

            raise ValueError(
                f"{tls}: "
                f"stage1 + stage2 "
                f"does not equal "
                f"TOTAL_EFFECTIVE_GREEN"
            )

        # Offset should remain inside
        # one normalized cycle
        if abs(offset) > (
            cycle_length / 2
        ):

            raise ValueError(
                f"{tls}: invalid offset "
                f"{offset}"
            )


    # =====================================================
    # 4. PROFILE-LENGTH CHECKS
    # =====================================================

    for (
        approach_id,
        approach
    ) in scoot_approaches.items():

        profile_names = [
            "flow_profile",
            "occupancy_profile",
            "arrival_profile",
            "dispersed_arrival_profile",
            "queue_profile"
        ]

        for profile_name in (
            profile_names
        ):

            if (
                len(
                    approach[
                        profile_name
                    ]
                )
                != cycle_length
            ):

                raise ValueError(
                    f"{approach_id}: "
                    f"{profile_name} "
                    f"length != "
                    f"{cycle_length}"
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

                # Vehicles left unserved from previous cycle
                "residual_queue": 0.0,

                # Demand + residual queue
                "effective_demand_per_cycle": 0.0,

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

def update_cyclic_flow_profiles(cycle_position):

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
    actual_offset = scoot_node_state[tls]["offset"]
    return is_approach_green_at_offset(tls, side_index, cycle_second, actual_offset)


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

    # =====================================================
    # MOVEMENT / LANE LEVEL SATURATION
    #
    # Lane 0 = Right
    # Lane 1 = Straight
    # Lane 2 = Left
    # =====================================================

    lane_residual_queues = (
        approach.get(
            "lane_residual_queues",
            [0.0, 0.0, 0.0]
        )
    )

    lane_demands = [
        0.0,
        0.0,
        0.0
    ]

    lane_saturations = [
        0.0,
        0.0,
        0.0
    ]

    # Capacity of ONE lane during its green
    lane_capacity = (
        SATURATION_FLOW_PER_LANE
        * effective_green
    )

    # =====================================================
    # Get demand separately from each detector/lane
    # =====================================================

    for detector_id in approach["detectors"]:

        detector = (
            scoot_detectors[
                detector_id
            ]
        )

        lane_id = detector[
            "lane_id"
        ]

        # SUMO lane IDs end with:
        # _0 = Right
        # _1 = Straight
        # _2 = Left
        lane_index = int(
            lane_id.rsplit(
                "_",
                1
            )[1]
        )

        # Use approximately one active cycle
        # of observed detector flow.
        recent_flow = (
            detector[
                "flow_history"
            ][
                -cycle_length:
            ]
        )

        lane_demand = sum(
            recent_flow
        )

        lane_demands[
            lane_index
        ] = lane_demand

    # =====================================================
    # Calculate saturation separately for each lane
    # =====================================================

    for lane_index in range(
        NUM_LANES
    ):

        effective_lane_demand = (
            lane_demands[
                lane_index
            ]
            +
            lane_residual_queues[
                lane_index
            ]
        )

        if lane_capacity > 0:

            lane_saturations[
                lane_index
            ] = (
                effective_lane_demand
                / lane_capacity
            )

        elif effective_lane_demand > 0:

            lane_saturations[
                lane_index
            ] = float("inf")

        else:

            lane_saturations[
                lane_index
            ] = 0.0

    # =====================================================
    # Critical movement controls approach saturation
    # =====================================================

    degree_of_saturation = max(
        lane_saturations
    )

    critical_lane = (
        lane_saturations.index(
            degree_of_saturation
        )
    )

    # Save these for debugging
    approach[
        "lane_demands"
    ] = lane_demands

    approach[
        "lane_saturations"
    ] = lane_saturations

    approach[
        "critical_lane"
    ] = critical_lane

    # Keep the old approach-level bookkeeping
    # so the rest of your code does not break.
    demand_per_cycle = sum(
        lane_demands
    )

    capacity_per_cycle = (
        lane_capacity
        * approach["num_lanes"]
    )

    return (
        degree_of_saturation,
        demand_per_cycle,
        capacity_per_cycle
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
            effective_demand
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
        approach["effective_demand_per_cycle"] = demand_per_cycle + approach.get("residual_queue", 0.0)


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

def get_actual_local_cycle_second(tls, regional_second):
    offset = scoot_node_state[tls]["offset"]
    return (regional_second - offset) % cycle_length

def apply_signal_state(tls, local_second):
    stage1_green = scoot_node_state[tls]["stage1_green"]
    stage2_start = stage1_green + 5

    if tls in TLS_REG:
        if local_second < stage1_green:
            state = "GGgrrrGGgrrr"

        elif local_second < stage1_green + 4:
            state = "yyyrrryyyrrr"
            
        elif local_second < stage1_green + 5:
            state = "rrrrrrrrrrrr"

        elif local_second < cycle_length - 5:
            state = "rrrGGgrrrGGg"

        elif local_second < cycle_length - 1:
            state = "rrryyyrrryyy"

        else:
            state = "rrrrrrrrrrrr"

    # ==================================================
    # INVERTED B1
    # ==================================================

    else:
        if local_second < stage1_green:
            state = "rrrGGgrrrGGg"

        elif local_second < stage1_green + 4:
            state = "rrryyyrrryyy"
            
        elif local_second < stage1_green + 5:
            state = "rrrrrrrrrrrr"

        elif local_second < cycle_length - 5:
            state = "GGgrrrGGgrrr"

        elif local_second < cycle_length - 1:
            state = "yyyrrryyyrrr"

        else:
            state = "rrrrrrrrrrrr"

    traci.trafficlight.setRedYellowGreenState(
        tls,
        state
    )

def apply_target_offsets():
    print("\n===== SCOOT OFFSETS APPLIED =====")

    scoot_node_state["A0"]["offset"] = 0

    # Apply offsets for every other signal but A0 since it is reference
    for tls in ["A1","B0","B1"]:

        old_offset = scoot_node_state[tls]["offset"]
        new_offset = scoot_node_state[tls]["target_offset"]

        new_offset = normalize_offset(new_offset)
        scoot_node_state[tls]["offset"] = new_offset

        print(
            f"{tls}: "
            f"{old_offset} -> "
            f"{new_offset} s"
        )

    print("===== END SCOOT OFFSETS APPLIED =====\n")

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

def get_actual_residual_queue(approach):
    tls = approach["tls"]
    side_index = approach["side_index"]
    tls_index = TLS_ORDER.index(tls)
    residual_queue = 0.0

    for lane_index in range(NUM_LANES):
        history = queue_lengths[tls_index][side_index][lane_index]

        if history:
            residual_queue += history[-1]

    return residual_queue

def snapshot_residual_queues():

    for approach_id, approach in scoot_approaches.items():

        tls = approach["tls"]
        side_index = approach["side_index"]

        tls_index = TLS_ORDER.index(tls)

        lane_residual_queues = []

        # Lane mapping:
        # 0 = Right
        # 1 = Straight
        # 2 = Left
        for lane_index in range(NUM_LANES):

            history = (
                queue_lengths[
                    tls_index
                ][
                    side_index
                ][
                    lane_index
                ]
            )

            if history:
                residual_queue = history[-1]
            else:
                residual_queue = 0.0

            lane_residual_queues.append(
                residual_queue
            )

        # Store each lane separately
        approach[
            "lane_residual_queues"
        ] = lane_residual_queues

        # Keep old total value too
        approach[
            "residual_queue"
        ] = sum(
            lane_residual_queues
        )

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
regional_cycle_second = 0

integration_enabled = False

split_history = {
    tls: []
    for tls in TLS_ORDER
}

offset_history = {
    tls: []
    for tls in TLS_ORDER
}

cycle_history = []

integration_history = []

validate_scoot_network()
validate_scoot_detectors()
validate_scoot_approaches()

while traci.simulation.getTime() < END_TIME:
    simStep()
    current_time = int(traci.simulation.getTime())

    update_cyclic_flow_profiles(regional_cycle_second)
    update_stopline_arrival_profiles()
    update_predicted_queue_profiles()
    update_degrees_of_saturation()
    update_performance_indices()

    if not model_ready:
        enough_samples = all(
            min(approach["samples"]) >= 1

            for approach in scoot_approaches.values()
        )

        if enough_samples:
            model_ready = True
            print("\n===== SCOOT MODEL READY =====")
            print(
                f"Model rebuilt for "
                f"{cycle_length}-second cycle."
            )
            print("===== END SCOOT MODEL READY =====\n")


    # 1. ENABLE FULL INTEGRATION AFTER INITIAL LEARNING

    if (not integration_enabled and current_time >= 240):
        integration_enabled = True
        print("\n===== SCOOT INTEGRATION ENABLED =====\n")


    # 2. SPLIT OPTIMIZER

    if (model_ready and regional_cycle_second == 0 and current_time >= cycle_length):

        for tls in TLS_ORDER:
            decision, candidate_scores, improvement = optimize_split(tls)
            validate_split_timings()

            split_history[tls].append(
                {
                    "time":
                        current_time,

                    "decision":
                        decision,

                    "stage1_green":
                        scoot_node_state[
                            tls
                        ][
                            "stage1_green"
                        ],

                    "stage2_green":
                        scoot_node_state[
                            tls
                        ][
                            "stage2_green"
                        ],

                    "scores":
                        candidate_scores.copy(),

                    "improvement":
                        improvement
                }
            )

    # 3. OFFSET OPTIMIZER

    if (model_ready and regional_cycle_second == 0 and current_time >= 240):
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

    # 4. REGIONAL CYCLE OPTIMIZER

    if (model_ready and current_time >= CYCLE_OPTIMIZER_INTERVAL and current_time % CYCLE_OPTIMIZER_INTERVAL == 0):

        (
            decision,
            target_cycle,
            critical_node,
            node_results

        ) = optimize_region_cycle(
            "R0"
        )

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


    # 5. APPLY CURRENT REAL SIGNAL STATES

    for tls in TLS_ORDER:

        local_second = (
            get_actual_local_cycle_second(
                tls,
                regional_cycle_second
            )
        )

        apply_signal_state(
            tls,
            local_second
        )
    
    validate_integrated_scoot()

    # ====================================================
    # 6. REGIONAL CYCLE BOUNDARY
    #
    # Apply new cycle + offsets ONLY here.
    # ====================================================

    regional_cycle_second += 1

    if (
        regional_cycle_second
        >= cycle_length
    ):

        regional_cycle_second = 0
        snapshot_residual_queues()

        if integration_enabled:

            apply_target_region_cycle(
                "R0"
            )

            apply_target_offsets()

            # Make sure the first state of the
            # newly applied timing plan is active
            # before the next SUMO second begins.
            for tls in TLS_ORDER:

                local_second = (
                    get_actual_local_cycle_second(
                        tls,
                        regional_cycle_second
                    )
                )

                apply_signal_state(
                    tls,
                    local_second
                )

            integration_history.append(
                {
                    "time":
                        current_time,

                    "cycle":
                        cycle_length,

                    "offsets": {
                        tls:
                            scoot_node_state[
                                tls
                            ][
                                "offset"
                            ]

                        for tls in TLS_ORDER
                    },

                    "splits": {
                        tls: (
                            scoot_node_state[
                                tls
                            ][
                                "stage1_green"
                            ],

                            scoot_node_state[
                                tls
                            ][
                                "stage2_green"
                            ]
                        )

                        for tls in TLS_ORDER
                    }
                }
            )

def print_integration_summary():

    print(
        "\n===== SCOOT INTEGRATION CHECK ====="
    )

    if not integration_history:

        print(
            "No integrated timing changes applied."
        )

    for record in integration_history:

        print(
            f"\nt={record['time']}: "
            f"active cycle="
            f"{record['cycle']} s"
        )

        print(
            f"  offsets: "
            f"{record['offsets']}"
        )

        print(
            f"  splits: "
            f"{record['splits']}"
        )

    print(
        "\n===== END SCOOT INTEGRATION CHECK =====\n"
    )

def print_final_scoot_state():

    print(
        "\n===== FINAL SCOOT STATE ====="
    )

    print(
        f"Active regional cycle: "
        f"{cycle_length} s"
    )

    print(
        f"Target regional cycle: "
        f"{scoot_region_state['R0']['target_cycle_length']} s"
    )

    print("\nNodes:")

    for tls in TLS_ORDER:

        print(
            f"  {tls}: "
            f"stage1="
            f"{scoot_node_state[tls]['stage1_green']} s, "
            f"stage2="
            f"{scoot_node_state[tls]['stage2_green']} s, "
            f"offset="
            f"{scoot_node_state[tls]['offset']} s, "
            f"target_offset="
            f"{scoot_node_state[tls]['target_offset']} s"
        )

    print(
        "\n===== END FINAL SCOOT STATE =====\n"
    )

def print_scoot_experiment_summary():

    print(
        "\n===== SCOOT CONTROLLER SUMMARY ====="
    )

    print(
        f"Final active cycle: "
        f"{cycle_length} s"
    )

    print(
        f"Final target cycle: "
        f"{scoot_region_state['R0']['target_cycle_length']} s"
    )

    print("\nFinal signal timings:")

    for tls in TLS_ORDER:

        print(
            f"  {tls}: "
            f"split="
            f"{scoot_node_state[tls]['stage1_green']}/"
            f"{scoot_node_state[tls]['stage2_green']} s | "
            f"offset="
            f"{scoot_node_state[tls]['offset']} s"
        )

    print(
        "\n===== END SCOOT CONTROLLER SUMMARY =====\n"
    )

print_integration_summary()
print_final_scoot_state()
print_scoot_experiment_summary()

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