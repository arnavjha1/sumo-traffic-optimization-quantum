import traci
from collections import defaultdict
from annealer_classical import quantum_decision
from simulation_metrics import (
    PerformanceTracker,
    collect_queue_lengths_4d,
    should_continue_simulation,
    start_sumo,
    ROUTE_GENERATION_END,
    MAX_SIM_TIME,
    HOUR_SECONDS,
    NUM_HOURS,
)

SUMO_BINARY = "sumo"
SUMO_CONFIG = "sim2x2_data.sumocfg"

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

TLS_NEIGHBORS = [
    ["A0", "B0", "A1"],  # A0 neighbors
    ["A1", "B1", "A0"],  # A1 neighbors
    ["B0", "A0", "B1"],  # B0 neighbors
    ["B1", "A1", "B0"]   # B1 neighbors
]

start_sumo(SUMO_BINARY, SUMO_CONFIG, max_depart_delay=300)

# -----------------------
# FORCE MANUAL TLS CONTROL
# -----------------------
for tls in TLS_ORDER:
    traci.trafficlight.setProgram(tls, "0")
    traci.trafficlight.setPhaseDuration(tls, 999999)

# -----------------------
# DATA STRUCTURES
# -----------------------
depart_time = {}
route_of = {}
last_waiting_time = {}

travel_times = defaultdict(list)
waiting_times = defaultdict(list)
throughput = defaultdict(int)
hourly_travel_times = [[] for _ in range(NUM_HOURS)]
hourly_waiting_times = [[] for _ in range(NUM_HOURS)]
hourly_throughput = [0 for _ in range(NUM_HOURS)]

NUM_TLS = 4
NUM_SIDES = 4       # Each TLS has 4 incoming sides
NUM_LANES = 3       # Left=2, Straight=1, Right=0

# Initialize 4D queue_lengths: TLS x Side x Lane x Time
queue_lengths = [[ [ [] for _ in range(NUM_LANES) ] for _ in range(NUM_SIDES) ] for _ in range(NUM_TLS)]
regular_cars = [[ [ [] for _ in range(NUM_LANES) ] for _ in range(NUM_SIDES) ] for _ in range(NUM_TLS)]
tIndex = []
bias_i_tls = [[] for _ in range(NUM_TLS)]  # Store bias_i values for each TLS over time

for tls in TLS_REG:
    traci.trafficlight.setRedYellowGreenState(tls, "GGgrrrGGgrrr")
    tIndex.append(tls)
    
for tls in TLS_INVERT:
    traci.trafficlight.setRedYellowGreenState(tls, "rrrGGgrrrGGg")
    tIndex.append(tls)

metrics = PerformanceTracker("quantum")

def simStep(num_times=1):
    for _ in range(num_times):
        traci.simulationStep()
        departed_count, arrived_count = metrics.process_vehicle_events()
        total_queue_now = collect_queue_lengths_4d(
            TLS_ORDER,
            NUM_SIDES,
            NUM_LANES,
            queue_lengths,
            regular_cars=regular_cars,
        )
        metrics.sample_debug(total_queue_now, departed_count, arrived_count)

QUEUE_K = 2
DISCHARGE_QUEUE_K = 1
REG_K = 1
LEFT_WEIGHT = 1.00
RIGHT_WEIGHT = 0.47
pressure = [[ [] for _ in range(NUM_SIDES) ] for _ in range(NUM_TLS)]
discharging_pressure = [[ [] for _ in range(NUM_SIDES) ] for _ in range(NUM_TLS)]

def compute_pressure():
    for tls in TLS_ORDER:
        tls_index = tIndex.index(tls)
        for side_index in range(NUM_SIDES):
            left_queue     = queue_lengths[tls_index][side_index][2][-1]
            left_reg       =  regular_cars[tls_index][side_index][2][-1]
            straight_queue = queue_lengths[tls_index][side_index][1][-1]
            straight_reg   =  regular_cars[tls_index][side_index][1][-1]
            right_queue    = queue_lengths[tls_index][side_index][0][-1]
            right_reg      =  regular_cars[tls_index][side_index][0][-1]

            pressure_value = QUEUE_K * (LEFT_WEIGHT * left_queue + straight_queue + RIGHT_WEIGHT * right_queue) + REG_K * (LEFT_WEIGHT * left_reg + straight_reg + RIGHT_WEIGHT * right_reg)
            pressure[tls_index][side_index].append(pressure_value)

def compute_discharging_pressure():
    for tls in TLS_ORDER:
        tls_index = tIndex.index(tls)
        for side_index in range(NUM_SIDES):
            left_queue     = queue_lengths[tls_index][side_index][2][-1]
            left_reg       =  regular_cars[tls_index][side_index][2][-1]
            straight_queue = queue_lengths[tls_index][side_index][1][-1]
            straight_reg   =  regular_cars[tls_index][side_index][1][-1]
            right_queue    = queue_lengths[tls_index][side_index][0][-1]
            right_reg      =  regular_cars[tls_index][side_index][0][-1]

            pressure_value = DISCHARGE_QUEUE_K * (LEFT_WEIGHT * left_queue + straight_queue + RIGHT_WEIGHT * right_queue) + REG_K * (LEFT_WEIGHT * left_reg + straight_reg + RIGHT_WEIGHT * right_reg)
            discharging_pressure[tls_index][side_index].append(pressure_value)


x_i = [[] for _ in range(NUM_TLS)]

# -----------------------
# SIMULATION LOOP
# -----------------------
sim_module = [0] * len(tIndex)  # Track which module each TLS is in
MIN_CHANGE_TIME = 12  # Minimum time to wait before allowing another change

while should_continue_simulation():

    simStep()
    compute_pressure()
    compute_discharging_pressure()


    # ====================================================
    # QUEUE LENGTH ALGORITHM
    for tls in TLS_REG:
        current_state = traci.trafficlight.getRedYellowGreenState(tls)
        t = traci.simulation.getTime()

        if(current_state == "GGgrrrGGgrrr"):
            bias_i = (discharging_pressure[tIndex.index(tls)][0][-1] + discharging_pressure[tIndex.index(tls)][2][-1]) - (pressure[tIndex.index(tls)][1][-1] + pressure[tIndex.index(tls)][3][-1])
        elif(current_state == "rrrGGgrrrGGg"):
            bias_i = (pressure[tIndex.index(tls)][0][-1] + pressure[tIndex.index(tls)][2][-1]) - (discharging_pressure[tIndex.index(tls)][1][-1] + discharging_pressure[tIndex.index(tls)][3][-1])
        else:
            bias_i = (pressure[tIndex.index(tls)][0][-1] + pressure[tIndex.index(tls)][2][-1]) - (pressure[tIndex.index(tls)][1][-1] + pressure[tIndex.index(tls)][3][-1])
        
        bias_i_tls[tIndex.index(tls)].append(bias_i)

        if sim_module[tIndex.index(tls)] >= 0 and sim_module[tIndex.index(tls)] < 55:
            traci.trafficlight.setRedYellowGreenState(tls, "GGgrrrGGgrrr")
            if(sim_module[tIndex.index(tls)] >= MIN_CHANGE_TIME and x_i[tIndex.index(tls)][-1] == -1):
                sim_module[tIndex.index(tls)] = 55
            else:
                sim_module[tIndex.index(tls)] += 1

        elif sim_module[tIndex.index(tls)] >= 55 and sim_module[tIndex.index(tls)] < 59:
            traci.trafficlight.setRedYellowGreenState(tls, "yyyrrryyyrrr")
            sim_module[tIndex.index(tls)] += 1

        elif sim_module[tIndex.index(tls)] >= 59 and sim_module[tIndex.index(tls)] < 60:
            traci.trafficlight.setRedYellowGreenState(tls, "rrrrrrrrrrrr")
            sim_module[tIndex.index(tls)] += 1

        elif sim_module[tIndex.index(tls)] >= 60 and sim_module[tIndex.index(tls)] < 115:
            traci.trafficlight.setRedYellowGreenState(tls, "rrrGGgrrrGGg")
            if(sim_module[tIndex.index(tls)] >= (MIN_CHANGE_TIME + 60) and x_i[tIndex.index(tls)][-1] == 1):
                sim_module[tIndex.index(tls)] = 115
            else:
                sim_module[tIndex.index(tls)] += 1
                
        elif sim_module[tIndex.index(tls)] >= 115 and sim_module[tIndex.index(tls)] < 119:
            traci.trafficlight.setRedYellowGreenState(tls, "rrryyyrrryyy")
            sim_module[tIndex.index(tls)] += 1

        elif sim_module[tIndex.index(tls)] >= 119 and sim_module[tIndex.index(tls)] < 120:
            traci.trafficlight.setRedYellowGreenState(tls, "rrrrrrrrrrrr")
            sim_module[tIndex.index(tls)] = 0

    for tls in TLS_INVERT:
        current_state = traci.trafficlight.getRedYellowGreenState(tls)
        t = traci.simulation.getTime()

        if(current_state == "GGgrrrGGgrrr"):
            bias_i = (discharging_pressure[tIndex.index(tls)][0][-1] + discharging_pressure[tIndex.index(tls)][2][-1]) - (pressure[tIndex.index(tls)][1][-1] + pressure[tIndex.index(tls)][3][-1])
        elif(current_state == "rrrGGgrrrGGg"):
            bias_i = (pressure[tIndex.index(tls)][0][-1] + pressure[tIndex.index(tls)][2][-1]) - (discharging_pressure[tIndex.index(tls)][1][-1] + discharging_pressure[tIndex.index(tls)][3][-1])
        else:
            bias_i = (pressure[tIndex.index(tls)][0][-1] + pressure[tIndex.index(tls)][2][-1]) - (pressure[tIndex.index(tls)][1][-1] + pressure[tIndex.index(tls)][3][-1])
        
        bias_i_tls[tIndex.index(tls)].append(bias_i)

        
        if sim_module[tIndex.index(tls)] >= 0 and sim_module[tIndex.index(tls)] < 55:
            traci.trafficlight.setRedYellowGreenState(tls, "rrrGGgrrrGGg")
            if(sim_module[tIndex.index(tls)] >= MIN_CHANGE_TIME and x_i[tIndex.index(tls)][-1] == 1):
                sim_module[tIndex.index(tls)] = 55
            else:
                sim_module[tIndex.index(tls)] += 1
                
        elif sim_module[tIndex.index(tls)] >= 55 and sim_module[tIndex.index(tls)] < 59:
            traci.trafficlight.setRedYellowGreenState(tls, "rrryyyrrryyy")
            sim_module[tIndex.index(tls)] += 1

        elif sim_module[tIndex.index(tls)] >= 59 and sim_module[tIndex.index(tls)] < 60:
            traci.trafficlight.setRedYellowGreenState(tls, "rrrrrrrrrrrr")
            sim_module[tIndex.index(tls)] += 1

        elif sim_module[tIndex.index(tls)] >= 60 and sim_module[tIndex.index(tls)] < 115:
            traci.trafficlight.setRedYellowGreenState(tls, "GGgrrrGGgrrr")
            if(sim_module[tIndex.index(tls)] >= (MIN_CHANGE_TIME + 60) and x_i[tIndex.index(tls)][-1] == -1):
                sim_module[tIndex.index(tls)] = 115
            else:
                sim_module[tIndex.index(tls)] += 1

        elif sim_module[tIndex.index(tls)] >= 115 and sim_module[tIndex.index(tls)] < 119:
            traci.trafficlight.setRedYellowGreenState(tls, "yyyrrryyyrrr")
            sim_module[tIndex.index(tls)] += 1

        elif sim_module[tIndex.index(tls)] >= 119 and sim_module[tIndex.index(tls)] < 120:
            traci.trafficlight.setRedYellowGreenState(tls, "rrrrrrrrrrrr")
            sim_module[tIndex.index(tls)] = 0
    
    # ====================================================
    # QUANTUM ANNEALING OPTIMIZATION
    # ====================================================

    # Convert biases to a flat list (length 4)
    bias_list = [bias_i_tls[tIndex.index(tls)][-1] for tls in TLS_ORDER]

    # Previous traffic light states
    # 0 = NS green
    # 1 = EW green

    prev_state = []

    for i in range(NUM_TLS):

        # First timestep fallback
        if len(x_i[i]) == 0:

            # Use initial configuration
            if TLS_ORDER[i] in TLS_REG:
                prev_state.append(0)
            else:
                prev_state.append(1)

        else:

            # Convert {-1,1} -> {0,1}
            prev_state.append(
                1 if x_i[i][-1] == 1 else 0
            )
    
    neighbor_indices = []

    for i in range(NUM_TLS):

        curr_neighbors = []

        for neighbor_tls in TLS_NEIGHBORS[i][1:]:

            curr_neighbors.append(
                tIndex.index(neighbor_tls)
            )

        neighbor_indices.append(curr_neighbors)

    bitstring = quantum_decision(
        bias_list,
        prev_state,
        neighbor_indices,
        coupling_strength=2
    )

    if int(traci.simulation.getTime()) % 3600 == 0:
        print(f"Quantum simulation time: {traci.simulation.getTime()}")

    # Update x_i with quantum decisions
    for idx, tls in enumerate(TLS_ORDER):
        x_i[idx].append(1 if bitstring[idx] == '1' else -1)
    # ====================================================

traci.close()

metrics.save_and_print()
