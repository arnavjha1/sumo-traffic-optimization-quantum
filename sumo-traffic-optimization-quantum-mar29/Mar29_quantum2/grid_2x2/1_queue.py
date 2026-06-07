import traci
from collections import defaultdict
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

SUMO_BINARY = "sumo-gui"
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
tIndex = []

for tls in TLS_REG:
    traci.trafficlight.setRedYellowGreenState(tls, "GGgrrrGGgrrr")
    tIndex.append(tls)
    
for tls in TLS_INVERT:
    traci.trafficlight.setRedYellowGreenState(tls, "rrrGGgrrrGGg")
    tIndex.append(tls)

metrics = PerformanceTracker("queue")

def simStep(num_times=1):
    for _ in range(num_times):
        traci.simulationStep()
        departed_count, arrived_count = metrics.process_vehicle_events()
        total_queue_now = collect_queue_lengths_4d(
            TLS_ORDER,
            NUM_SIDES,
            NUM_LANES,
            queue_lengths,
            regular_cars=None,
        )
        metrics.sample_debug(total_queue_now, departed_count, arrived_count)

# -----------------------
# SIMULATION LOOP
# -----------------------
sim_module = [0] * len(tIndex)  # Track which module each TLS is in

while should_continue_simulation():

    simStep()


    # ====================================================
    # QUEUE LENGTH ALGORITHM
    
    for tls in TLS_REG:
        current_state = traci.trafficlight.getRedYellowGreenState(tls)
        t = traci.simulation.getTime()
        ns_queue = queue_lengths[tIndex.index(tls)][0][1][-1] + queue_lengths[tIndex.index(tls)][0][2][-1] + queue_lengths[tIndex.index(tls)][0][0][-1] + queue_lengths[tIndex.index(tls)][2][1][-1] + queue_lengths[tIndex.index(tls)][2][2][-1] + queue_lengths[tIndex.index(tls)][2][0][-1]
        ew_queue = queue_lengths[tIndex.index(tls)][1][1][-1] + queue_lengths[tIndex.index(tls)][1][2][-1] + queue_lengths[tIndex.index(tls)][1][0][-1] + queue_lengths[tIndex.index(tls)][3][1][-1] + queue_lengths[tIndex.index(tls)][3][2][-1] + queue_lengths[tIndex.index(tls)][3][0][-1]
        
        if sim_module[tIndex.index(tls)] >= 0 and sim_module[tIndex.index(tls)] < 55:
            traci.trafficlight.setRedYellowGreenState(tls, "GGgrrrGGgrrr")
            if(sim_module[tIndex.index(tls)] >= 23 and ns_queue < 10):
                sim_module[tIndex.index(tls)] = 55
            else:
                sim_module[tIndex.index(tls)] += 1

        elif sim_module[tIndex.index(tls)] >= 55 and sim_module[tIndex.index(tls)] < 59:
            traci.trafficlight.setRedYellowGreenState(tls, "yyyrrryyyrrr")
            sim_module[tIndex.index(tls)] += 1

        elif sim_module[tIndex.index(tls)] == 59:
            traci.trafficlight.setRedYellowGreenState(tls, "rrrrrrrrrrrr")
            sim_module[tIndex.index(tls)] += 1

        elif sim_module[tIndex.index(tls)] >= 60 and sim_module[tIndex.index(tls)] < 115:
            traci.trafficlight.setRedYellowGreenState(tls, "rrrGGgrrrGGg")
            if(sim_module[tIndex.index(tls)] >= 83 and ew_queue < 10):
                sim_module[tIndex.index(tls)] = 115
            else:
                sim_module[tIndex.index(tls)] += 1
                
        elif sim_module[tIndex.index(tls)] >= 115 and sim_module[tIndex.index(tls)] < 119:
            traci.trafficlight.setRedYellowGreenState(tls, "rrryyyrrryyy")
            sim_module[tIndex.index(tls)] += 1

        elif sim_module[tIndex.index(tls)] == 119:
            traci.trafficlight.setRedYellowGreenState(tls, "rrrrrrrrrrrr")
            sim_module[tIndex.index(tls)] = 0

    for tls in TLS_INVERT:
        current_state = traci.trafficlight.getRedYellowGreenState(tls)
        t = traci.simulation.getTime()
        ew_queue = queue_lengths[tIndex.index(tls)][0][1][-1] + queue_lengths[tIndex.index(tls)][0][2][-1] + queue_lengths[tIndex.index(tls)][0][0][-1] + queue_lengths[tIndex.index(tls)][2][1][-1] + queue_lengths[tIndex.index(tls)][2][2][-1] + queue_lengths[tIndex.index(tls)][2][0][-1]
        ns_queue = queue_lengths[tIndex.index(tls)][1][1][-1] + queue_lengths[tIndex.index(tls)][1][2][-1] + queue_lengths[tIndex.index(tls)][1][0][-1] + queue_lengths[tIndex.index(tls)][3][1][-1] + queue_lengths[tIndex.index(tls)][3][2][-1] + queue_lengths[tIndex.index(tls)][3][0][-1]
        
        if sim_module[tIndex.index(tls)] >= 0 and sim_module[tIndex.index(tls)] < 55:
            traci.trafficlight.setRedYellowGreenState(tls, "rrrGGgrrrGGg")
            if(sim_module[tIndex.index(tls)] >= 23 and ns_queue < 10):
                sim_module[tIndex.index(tls)] = 55
            else:
                sim_module[tIndex.index(tls)] += 1

        elif sim_module[tIndex.index(tls)] >= 55 and sim_module[tIndex.index(tls)] < 59:
            traci.trafficlight.setRedYellowGreenState(tls, "rrryyyrrryyy")
            sim_module[tIndex.index(tls)] += 1

        elif sim_module[tIndex.index(tls)] == 59:
            traci.trafficlight.setRedYellowGreenState(tls, "rrrrrrrrrrrr")
            sim_module[tIndex.index(tls)] += 1

        elif sim_module[tIndex.index(tls)] >= 60 and sim_module[tIndex.index(tls)] < 115:
            traci.trafficlight.setRedYellowGreenState(tls, "GGgrrrGGgrrr")
            if(sim_module[tIndex.index(tls)] >= 83 and ew_queue < 10):
                sim_module[tIndex.index(tls)] = 115
            else:
                sim_module[tIndex.index(tls)] += 1
                
        elif sim_module[tIndex.index(tls)] >= 115 and sim_module[tIndex.index(tls)] < 119:
            traci.trafficlight.setRedYellowGreenState(tls, "yyyrrryyyrrr")
            sim_module[tIndex.index(tls)] += 1

        elif sim_module[tIndex.index(tls)] == 119:
            traci.trafficlight.setRedYellowGreenState(tls, "rrrrrrrrrrrr")
            sim_module[tIndex.index(tls)] = 0
    # ====================================================

traci.close()

metrics.save_and_print()
