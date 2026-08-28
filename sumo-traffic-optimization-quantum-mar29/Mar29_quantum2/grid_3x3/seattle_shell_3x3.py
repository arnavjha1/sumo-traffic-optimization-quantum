"""
Canonical 3x3 Seattle evaluation shell.

Mirrors the already-run official 3x3 QAOA Seattle framing:
- 24-hour simulation: 86,400 s
- 900-s measurement warm-up excluded at the start of every hour
- random departure offset: 0-60 s
- completed vehicles attributed to departure hour
- no post-24h drain period
- same 3x3 TLS ordering / REG-INVERT orientation
"""

import traci
from collections import defaultdict

SUMO_BINARY = "sumo"
SUMO_CONFIG = "grid_3x3/sim3x3_data.sumocfg"

END_TIME = 86400
WARMUP_TIME = 900
RANDOM_DEPART_OFFSET = 60

HOUR_SECONDS = 3600
NUM_HOURS = 24

TLS_ORDER = [
    "A0", "A1", "A2",
    "B0", "B1", "B2",
    "C0", "C1", "C2",
]

TLS_REG = ["A1", "B1", "B2", "C0", "C1", "C2"]
TLS_INVERT = ["A0", "A2", "B0"]

NUM_TLS = len(TLS_ORDER)
NUM_SIDES = 4
NUM_LANES = 3

PHASE_NS = "GGgrrrGGgrrr"
PHASE_EW = "rrrGGgrrrGGg"
YELLOW_NS_TO_EW = "yyyrrryyyrrr"
YELLOW_EW_TO_NS = "rrryyyrrryyy"
ALL_RED = "rrrrrrrrrrrr"

sumo_cmd = [
    SUMO_BINARY,
    "-c", SUMO_CONFIG,
    "--random-depart-offset", str(RANDOM_DEPART_OFFSET),
]

traci.start(sumo_cmd)

for tls in TLS_ORDER:
    traci.trafficlight.setProgram(tls, "0")
    traci.trafficlight.setPhaseDuration(tls, 999999)

for tls in TLS_REG:
    traci.trafficlight.setRedYellowGreenState(tls, PHASE_NS)

for tls in TLS_INVERT:
    traci.trafficlight.setRedYellowGreenState(tls, PHASE_EW)

# -----------------------
# CANONICAL SEATTLE METRICS
# -----------------------
depart_time = {}
depart_hour = {}
last_waiting_time = {}

travel_times_by_hour = defaultdict(list)
waiting_times_by_hour = defaultdict(list)
completed_vehicles_by_hour = defaultdict(int)
measured_departures_by_hour = defaultdict(int)

# ============================================================
# CONTROLLER-SPECIFIC SETUP GOES HERE
# ============================================================


def sim_step():
    """
    Advance SUMO by one second and collect the same Seattle measurement
    framing used by the official 3x3 QAOA Seattle evaluator.
    """
    traci.simulationStep()
    t = traci.simulation.getTime()

    local_time = int(t % HOUR_SECONDS)

    for veh in traci.simulation.getDepartedIDList():
        if local_time >= WARMUP_TIME:
            hour = int(t // HOUR_SECONDS)

            if 0 <= hour < NUM_HOURS:
                depart_time[veh] = t
                depart_hour[veh] = hour
                last_waiting_time[veh] = 0.0
                measured_departures_by_hour[hour] += 1

    for veh in traci.vehicle.getIDList():
        if veh in depart_time:
            last_waiting_time[veh] = (
                traci.vehicle.getAccumulatedWaitingTime(veh)
            )

    for veh in traci.simulation.getArrivedIDList():
        if veh in depart_time:
            travel_time = t - depart_time[veh]
            waiting_time = last_waiting_time.get(veh, 0.0)
            hour = depart_hour[veh]

            travel_times_by_hour[hour].append(travel_time)
            waiting_times_by_hour[hour].append(waiting_time)
            completed_vehicles_by_hour[hour] += 1

            depart_time.pop(veh, None)
            depart_hour.pop(veh, None)
            last_waiting_time.pop(veh, None)

    return int(t)


def controller_step(current_time):
    """
    Replace ONLY this function and the controller-specific setup section
    with logic from the corresponding working 3x3 controller.

    Do not call traci.simulationStep() here.
    Control continues during warm-up; only metric collection is excluded.
    """
    pass


try:
    while traci.simulation.getTime() < END_TIME:
        current_time = sim_step()

        controller_step(current_time)

        if current_time % HOUR_SECONDS == 0:
            print(
                f"t={current_time:5d} s | "
                f"hour={min(current_time // HOUR_SECONDS, 24):02d} | "
                f"measured_departed={sum(measured_departures_by_hour.values())} | "
                f"measured_completed={sum(completed_vehicles_by_hour.values())} | "
                f"active={traci.vehicle.getIDCount()}"
            )

finally:
    traci.close()


# -----------------------
# CANONICAL RESULTS
# -----------------------
print("\n===== 3x3 SEATTLE PERFORMANCE METRICS =====")
print(f"Simulation duration: {END_TIME} s")
print(f"Warm-up excluded: first {WARMUP_TIME} s of every hour")
print(f"Random departure offset: 0-{RANDOM_DEPART_OFFSET} s")

print("\nHourly Average Travel Time / Waiting Time:")

all_travel_times = []
all_waiting_times = []

for hour in range(NUM_HOURS):
    tt_values = travel_times_by_hour.get(hour, [])
    wt_values = waiting_times_by_hour.get(hour, [])

    measured_departures = measured_departures_by_hour.get(hour, 0)
    completed = completed_vehicles_by_hour.get(hour, 0)
    unfinished = measured_departures - completed

    if tt_values:
        avg_tt = sum(tt_values) / len(tt_values)
        avg_wt = sum(wt_values) / len(wt_values)

        all_travel_times.extend(tt_values)
        all_waiting_times.extend(wt_values)

        measurement_window = (
            f"{WARMUP_TIME}-3600 s "
            f"({(HOUR_SECONDS - WARMUP_TIME) // 60} min)"
        )

        print(
            f"Hour {hour:02d}: "
            f"TT={avg_tt:.2f} s, "
            f"WT={avg_wt:.2f} s, "
            f"n={len(tt_values)}, "
            f"departed={measured_departures}, "
            f"unfinished={unfinished}, "
            f"window={measurement_window}"
        )
    else:
        print(
            f"Hour {hour:02d}: "
            f"TT=N/A, WT=N/A, n=0, "
            f"departed={measured_departures}, "
            f"unfinished={unfinished}"
        )

if all_travel_times:
    overall_tt = sum(all_travel_times) / len(all_travel_times)
    overall_wt = sum(all_waiting_times) / len(all_waiting_times)
    total_completed = len(all_travel_times)
    total_measured_departures = sum(measured_departures_by_hour.values())

    print("\nPost-warm-up Overall:")
    print(f"Average Travel Time: {overall_tt:.2f} s")
    print(f"Average Waiting Time: {overall_wt:.2f} s")
    print(f"Measured completed vehicles: {total_completed}")
    print(f"Measured departures: {total_measured_departures}")
    print(
        f"Measured unfinished at t={END_TIME}: "
        f"{total_measured_departures - total_completed}"
    )
