import traci
from collections import defaultdict

SUMO_BINARY = "sumo-gui"
SUMO_CONFIG = "grid_3x3/sim3x3_data.sumocfg"

END_TIME = 86400          
WARMUP_TIME = 900         
RANDOM_DEPART_OFFSET = 60 

TLS_ORDER = [
    "A0", "A1", "A2",
    "B0", "B1", "B2",
    "C0", "C1", "C2",
]


TLS_REG = ["A1", "B1", "B2", "C0", "C1", "C2"]
TLS_INVERT = ["A0", "A2", "B0"]

NUM_TLS = len(TLS_ORDER)
NUM_SIDES = 4
NUM_LANES = 3       # Right=0, Straight=1, Left=2

cycle_length = 120

sumo_cmd = [
    SUMO_BINARY,
    "-c", SUMO_CONFIG,
    "--random-depart-offset", str(RANDOM_DEPART_OFFSET),
]

traci.start(sumo_cmd)

# Force manual TLS control.
for tls in TLS_ORDER:
    traci.trafficlight.setProgram(tls, "0")
    traci.trafficlight.setPhaseDuration(tls, 999999)


# ============================================================
# DATA STRUCTURES
# ============================================================

depart_time = {}
depart_hour = {}
last_waiting_time = {}

# Hour -> list of completed-vehicle travel/waiting times.
travel_times_by_hour = defaultdict(list)
waiting_times_by_hour = defaultdict(list)

completed_vehicles_by_hour = defaultdict(int)

queue_lengths = [
    [[[] for _ in range(NUM_LANES)] for _ in range(NUM_SIDES)]
    for _ in range(NUM_TLS)
]
regular_cars = [
    [[[] for _ in range(NUM_LANES)] for _ in range(NUM_SIDES)]
    for _ in range(NUM_TLS)
]

tIndex = []

for tls in TLS_REG:
    traci.trafficlight.setRedYellowGreenState(tls, "GGgrrrGGgrrr")
    tIndex.append(tls)

for tls in TLS_INVERT:
    traci.trafficlight.setRedYellowGreenState(tls, "rrrGGgrrrGGg")
    tIndex.append(tls)


def simStep(num_times=1):
    for _ in range(num_times):
        traci.simulationStep()
        t = traci.simulation.getTime()

        # --------------------------------------------------------
        # Vehicles that just departed
        # --------------------------------------------------------
        for veh in traci.simulation.getDepartedIDList():
            # IMPORTANT:
            # Vehicles entering before 600 s are deliberately ignored.
            if t >= WARMUP_TIME:
                depart_time[veh] = t
                depart_hour[veh] = int(t // 3600)
                last_waiting_time[veh] = 0.0

        # --------------------------------------------------------
        # Update waiting time only for vehicles we are measuring
        # --------------------------------------------------------
        active_measured = set(depart_time.keys())

        for veh in traci.vehicle.getIDList():
            if veh in active_measured:
                last_waiting_time[veh] = (
                    traci.vehicle.getAccumulatedWaitingTime(veh)
                )

        # --------------------------------------------------------
        # Vehicles that just arrived
        # --------------------------------------------------------
        for veh in traci.simulation.getArrivedIDList():
            if veh in depart_time:
                travel_time = t - depart_time[veh]
                waiting_time = last_waiting_time.get(veh, 0.0)

                # Attribute the vehicle to the hour in which it ENTERED.
                # Therefore hour 0 contains entries from 600-3599 s.
                hour = depart_hour[veh]

                travel_times_by_hour[hour].append(travel_time)
                waiting_times_by_hour[hour].append(waiting_time)
                completed_vehicles_by_hour[hour] += 1

                depart_time.pop(veh, None)
                depart_hour.pop(veh, None)
                last_waiting_time.pop(veh, None)

        # --------------------------------------------------------
        # Queue length debug collection
        # Skip all warm-up queue samples.
        # --------------------------------------------------------
        if (t % 3600) >= WARMUP_TIME:
            for tls_index, tls in enumerate(TLS_ORDER):
                lanes = traci.trafficlight.getControlledLanes(tls)
                lanes = list(dict.fromkeys(lanes))

                lanes_per_side = len(lanes) // NUM_SIDES

                for side_index in range(NUM_SIDES):
                    for lane_index in range(NUM_LANES):
                        lane_pos = side_index * lanes_per_side + lane_index

                        if lane_pos < len(lanes):
                            lane_id = lanes[lane_pos]
                            vehicle_ids = traci.lane.getLastStepVehicleIDs(lane_id)

                            queue = sum(
                                1 for veh in vehicle_ids
                                if traci.vehicle.getSpeed(veh) < 0.1
                            )
                            reg = sum(
                                1 for veh in vehicle_ids
                                if traci.vehicle.getSpeed(veh) >= 0.1
                            )

                            regular_cars[tls_index][side_index][lane_index].append(reg)
                            queue_lengths[tls_index][side_index][lane_index].append(queue)
                        else:
                            regular_cars[tls_index][side_index][lane_index].append(0)
                            queue_lengths[tls_index][side_index][lane_index].append(0)


# ============================================================
# SIMULATION LOOP
# ============================================================

sim_module = [0] * len(tIndex)

while traci.simulation.getTime() < END_TIME:
    simStep()

    # ------------------------------------------------------------
    # FIXED-TIME CONTROL
    # ------------------------------------------------------------

    for tls in TLS_REG:
        idx = tIndex.index(tls)

        if 0 <= sim_module[idx] < ((cycle_length / 2) - 5):
            traci.trafficlight.setRedYellowGreenState(tls, "GGgrrrGGgrrr")
            sim_module[idx] += 1

        elif ((cycle_length / 2) - 5) <= sim_module[idx] < ((cycle_length / 2) - 1):
            traci.trafficlight.setRedYellowGreenState(tls, "yyyrrryyyrrr")
            sim_module[idx] += 1

        elif ((cycle_length / 2) - 1) <= sim_module[idx] < (cycle_length / 2):
            traci.trafficlight.setRedYellowGreenState(tls, "rrrrrrrrrrrr")
            sim_module[idx] += 1

        elif (cycle_length / 2) <= sim_module[idx] < (cycle_length - 5):
            traci.trafficlight.setRedYellowGreenState(tls, "rrrGGgrrrGGg")
            sim_module[idx] += 1

        elif (cycle_length - 5) <= sim_module[idx] < (cycle_length - 1):
            traci.trafficlight.setRedYellowGreenState(tls, "rrryyyrrryyy")
            sim_module[idx] += 1

        elif (cycle_length - 1) <= sim_module[idx] < cycle_length:
            traci.trafficlight.setRedYellowGreenState(tls, "rrrrrrrrrrrr")
            sim_module[idx] = 0

    for tls in TLS_INVERT:
        idx = tIndex.index(tls)

        if 0 <= sim_module[idx] < ((cycle_length / 2) - 5):
            traci.trafficlight.setRedYellowGreenState(tls, "rrrGGgrrrGGg")
            sim_module[idx] += 1

        elif ((cycle_length / 2) - 5) <= sim_module[idx] < ((cycle_length / 2) - 1):
            traci.trafficlight.setRedYellowGreenState(tls, "rrryyyrrryyy")
            sim_module[idx] += 1

        elif ((cycle_length / 2) - 1) <= sim_module[idx] < (cycle_length / 2):
            traci.trafficlight.setRedYellowGreenState(tls, "rrrrrrrrrrrr")
            sim_module[idx] += 1

        elif (cycle_length / 2) <= sim_module[idx] < (cycle_length - 5):
            traci.trafficlight.setRedYellowGreenState(tls, "GGgrrrGGgrrr")
            sim_module[idx] += 1

        elif (cycle_length - 5) <= sim_module[idx] < (cycle_length - 1):
            traci.trafficlight.setRedYellowGreenState(tls, "yyyrrryyyrrr")
            sim_module[idx] += 1

        elif (cycle_length - 1) <= sim_module[idx] < cycle_length:
            traci.trafficlight.setRedYellowGreenState(tls, "rrrrrrrrrrrr")
            sim_module[idx] = 0


traci.close()

# ============================================================
# RESULTS
# ============================================================

print("\n===== 3x3 FIXED-TIME SEATTLE PERFORMANCE METRICS =====")
print(f"Simulation duration: {END_TIME} s")
print(f"Warm-up excluded: first {WARMUP_TIME} s")
print(f"Random departure offset: 0-{RANDOM_DEPART_OFFSET} s")

print("\nHourly Average Travel Time / Waiting Time:")

all_travel_times = []
all_waiting_times = []

for hour in range(24):
    tt_values = travel_times_by_hour.get(hour, [])
    wt_values = waiting_times_by_hour.get(hour, [])

    if tt_values:
        avg_tt = sum(tt_values) / len(tt_values)
        avg_wt = sum(wt_values) / len(wt_values)

        all_travel_times.extend(tt_values)
        all_waiting_times.extend(wt_values)

        measurement_window = "600-3600 s (50 min)" if hour == 0 else "full hour"

        print(
            f"Hour {hour:02d}: "
            f"TT={avg_tt:.2f} s, "
            f"WT={avg_wt:.2f} s, "
            f"n={len(tt_values)}, "
            f"window={measurement_window}"
        )
    else:
        print(f"Hour {hour:02d}: TT=N/A, WT=N/A, n=0")

if all_travel_times:
    overall_tt = sum(all_travel_times) / len(all_travel_times)
    overall_wt = sum(all_waiting_times) / len(all_waiting_times)

    print("\nPost-warm-up Overall:")
    print(f"Average Travel Time: {overall_tt:.2f} s")
    print(f"Average Waiting Time: {overall_wt:.2f} s")
    print(f"Measured completed vehicles: {len(all_travel_times)}")

# Queue lengths are optional diagnostics, not the primary Seattle result.
print("\nAverage Queue Length per TLS per Side/Lane (post-warm-up only):")
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