# FIXED-TIME

import traci

SUMO_BINARY = "sumo-gui"
SUMO_CONFIG = "grid_3x3/sim3x3_data.sumocfg"

END_TIME = 600
ALPHA_INDEX = 7
ROUTE_FILE = f"grid_3x3/routes_3x3/routes3x3_a{ALPHA_INDEX}.rou.xml"

TLS_ORDER = [
    "A0", "A1", "A2",
    "B0", "B1", "B2",
    "C0", "C1", "C2",
]

TLS_REG = ["A1", "B1", "B2", "C0", "C1", "C2"]
TLS_INVERT = ["A0", "A2", "B0"]

CYCLE_LENGTH = 120

sumo_cmd = [
    SUMO_BINARY,
    "-c", SUMO_CONFIG,
    "--route-files", ROUTE_FILE,
    "--end", str(END_TIME),
]

traci.start(sumo_cmd)

for tls in TLS_ORDER:
    traci.trafficlight.setProgram(tls, "0")
    traci.trafficlight.setPhaseDuration(tls, 999999)

for tls in TLS_REG:
    traci.trafficlight.setRedYellowGreenState(tls, "GGgrrrGGgrrr")

for tls in TLS_INVERT:
    traci.trafficlight.setRedYellowGreenState(tls, "rrrGGgrrrGGg")

sim_module = {tls: 0 for tls in TLS_ORDER}

depart_time = {}
last_waiting_time = {}

travel_times = []
waiting_times = []

total_departed = 0
total_arrived = 0


def sim_step():
    global total_departed, total_arrived

    traci.simulationStep()
    t = traci.simulation.getTime()

    for veh in traci.simulation.getDepartedIDList():
        depart_time[veh] = t
        last_waiting_time[veh] = 0.0
        total_departed += 1

    for veh in traci.vehicle.getIDList():
        if veh in depart_time:
            last_waiting_time[veh] = (
                traci.vehicle.getAccumulatedWaitingTime(veh)
            )

    for veh in traci.simulation.getArrivedIDList():
        if veh in depart_time:
            travel_time = t - depart_time[veh]
            waiting_time = last_waiting_time.get(veh, 0.0)

            travel_times.append(travel_time)
            waiting_times.append(waiting_time)

            total_arrived += 1

            depart_time.pop(veh, None)
            last_waiting_time.pop(veh, None)

    return t


def update_fixed_time_tls():
    for tls in TLS_REG:
        m = sim_module[tls]

        if 0 <= m < ((CYCLE_LENGTH / 2) - 5):
            traci.trafficlight.setRedYellowGreenState(tls, "GGgrrrGGgrrr")
            sim_module[tls] += 1

        elif ((CYCLE_LENGTH / 2) - 5) <= m < ((CYCLE_LENGTH / 2) - 1):
            traci.trafficlight.setRedYellowGreenState(tls, "yyyrrryyyrrr")
            sim_module[tls] += 1

        elif ((CYCLE_LENGTH / 2) - 1) <= m < (CYCLE_LENGTH / 2):
            traci.trafficlight.setRedYellowGreenState(tls, "rrrrrrrrrrrr")
            sim_module[tls] += 1

        elif (CYCLE_LENGTH / 2) <= m < (CYCLE_LENGTH - 5):
            traci.trafficlight.setRedYellowGreenState(tls, "rrrGGgrrrGGg")
            sim_module[tls] += 1

        elif (CYCLE_LENGTH - 5) <= m < (CYCLE_LENGTH - 1):
            traci.trafficlight.setRedYellowGreenState(tls, "rrryyyrrryyy")
            sim_module[tls] += 1

        elif (CYCLE_LENGTH - 1) <= m < CYCLE_LENGTH:
            traci.trafficlight.setRedYellowGreenState(tls, "rrrrrrrrrrrr")
            sim_module[tls] = 0

    for tls in TLS_INVERT:
        m = sim_module[tls]

        if 0 <= m < ((CYCLE_LENGTH / 2) - 5):
            traci.trafficlight.setRedYellowGreenState(tls, "rrrGGgrrrGGg")
            sim_module[tls] += 1

        elif ((CYCLE_LENGTH / 2) - 5) <= m < ((CYCLE_LENGTH / 2) - 1):
            traci.trafficlight.setRedYellowGreenState(tls, "rrryyyrrryyy")
            sim_module[tls] += 1

        elif ((CYCLE_LENGTH / 2) - 1) <= m < (CYCLE_LENGTH / 2):
            traci.trafficlight.setRedYellowGreenState(tls, "rrrrrrrrrrrr")
            sim_module[tls] += 1

        elif (CYCLE_LENGTH / 2) <= m < (CYCLE_LENGTH - 5):
            traci.trafficlight.setRedYellowGreenState(tls, "GGgrrrGGgrrr")
            sim_module[tls] += 1

        elif (CYCLE_LENGTH - 5) <= m < (CYCLE_LENGTH - 1):
            traci.trafficlight.setRedYellowGreenState(tls, "yyyrrryyyrrr")
            sim_module[tls] += 1

        elif (CYCLE_LENGTH - 1) <= m < CYCLE_LENGTH:
            traci.trafficlight.setRedYellowGreenState(tls, "rrrrrrrrrrrr")
            sim_module[tls] = 0


print("\n===== 3x3 FIXED-TIME SATURATED TEST =====")
print(f"Alpha case: a{ALPHA_INDEX} ({ALPHA_INDEX / 10:.1f})")
print(f"Route file: {ROUTE_FILE}")
print(f"Simulation duration: {END_TIME} s")

while traci.simulation.getTime() < END_TIME:
    t = sim_step()
    update_fixed_time_tls()

    if int(t) % 100 == 0:
        print(
            f"t={int(t):3d} s | "
            f"departed={total_departed} | "
            f"arrived={total_arrived} | "
            f"active={traci.vehicle.getIDCount()}"
        )

traci.close()

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
