import traci
from collections import defaultdict

SUMO_BINARY = "sumo-gui"
SUMO_CONFIG = "sim.sumocfg"
END_TIME = 600

# -----------------------
# FIXED OUTPUT ORDER
# -----------------------
ROUTE_ORDER = ["r0", "r1", "r2", "r3", "r4", "r5"]
TLS_ORDER = ["A0", "A1", "B0", "B1"]

traci.start([SUMO_BINARY, "-c", SUMO_CONFIG])

# -----------------------
# DATA STRUCTURES
# -----------------------
depart_time = {}
route_of = {}
last_waiting_time = {}

travel_times = defaultdict(list)
waiting_times = defaultdict(list)

queue_lengths = defaultdict(list)
throughput = defaultdict(int)

tls_ids = traci.trafficlight.getIDList()

# -----------------------
# SIMULATION LOOP
# -----------------------
while traci.simulation.getTime() < END_TIME:
    traci.simulationStep()
    t = traci.simulation.getTime()

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

            # cleanup
            depart_time.pop(veh, None)
            route_of.pop(veh, None)
            last_waiting_time.pop(veh, None)

    # Queue length per TLS
    for tls in tls_ids:
        queue = 0
        for lane in traci.trafficlight.getControlledLanes(tls):
            for veh in traci.lane.getLastStepVehicleIDs(lane):
                if traci.vehicle.getSpeed(veh) < 0.1:
                    queue += 1
        queue_lengths[tls].append(queue)

traci.close()

# -----------------------
# RESULTS (ORDERED)
# -----------------------
print("\n===== PERFORMANCE METRICS =====")

print("\nAverage Travel Time per Route:")
for route in ROUTE_ORDER:
    if route in travel_times and len(travel_times[route]) > 0:
        avg = sum(travel_times[route]) / len(travel_times[route])
        print(f"  {route}: {avg:.2f} s (n={len(travel_times[route])})")
    else:
        print(f"  {route}: N/A")

print("\nAverage Waiting Time per Route:")
for route in ROUTE_ORDER:
    if route in waiting_times and len(waiting_times[route]) > 0:
        avg = sum(waiting_times[route]) / len(waiting_times[route])
        print(f"  {route}: {avg:.2f} s")
    else:
        print(f"  {route}: N/A")

print("\nAverage Queue Length per Intersection:")
for tls in TLS_ORDER:
    if tls in queue_lengths and len(queue_lengths[tls]) > 0:
        avg = sum(queue_lengths[tls]) / len(queue_lengths[tls])
        print(f"  {tls}: {avg:.2f} vehicles")
    else:
        print(f"  {tls}: N/A")

print("\nThroughput:")
for route in ROUTE_ORDER:
    print(f"  {route}: {throughput.get(route, 0)}")
