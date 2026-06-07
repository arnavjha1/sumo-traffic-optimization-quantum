import csv
from pathlib import Path
from collections import defaultdict

import traci

SUMO_BINARY = "sumo-gui"
SUMO_CONFIG = "sim2x2_data.sumocfg"

ROUTE_GENERATION_END = 86400
MAX_SIM_TIME = 100000
HOUR_SECONDS = 3600
NUM_HOURS = 24

PROCESS_OUTPUT_DIR = Path("data_analysis") / "simulation_process_data"
PROCESS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HOURLY_DEBUG_CSV = PROCESS_OUTPUT_DIR / "fixed_hourly_debug.csv"
STEP_DEBUG_CSV = PROCESS_OUTPUT_DIR / "fixed_step_debug.csv"
METRICS_CSV = PROCESS_OUTPUT_DIR / "fixed_hourly_metrics.csv"

# -----------------------
# FIXED OUTPUT ORDER
# -----------------------
TWO_TURNS = [
    "r0", "r4", "r6", "r7", "r11", "r13", "r14", "r18", "r20", "r21",
    "r25", "r27", "r28", "r32", "r34", "r35", "r39", "r41", "r42",
    "r46", "r48", "r49", "r53", "r55",
]

ONE_TURN = [
    "r1", "r3", "r5", "r8", "r10", "r12", "r15", "r17", "r19", "r22",
    "r24", "r26", "r29", "r31", "r33", "r36", "r38", "r40", "r43",
    "r45", "r47", "r50", "r52", "r54",
]

NO_TURNS = ["r2", "r9", "r16", "r23", "r30", "r37", "r44", "r51"]

TLS_ORDER = ["A0", "A1", "B0", "B1"]

traci.start(
    [
        SUMO_BINARY,
        "-c",
        SUMO_CONFIG,
        "--max-depart-delay",
        "300",
    ]
)

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

hourly_departures = [0 for _ in range(NUM_HOURS)]
hourly_arrivals = [0 for _ in range(NUM_HOURS)]

hourly_active_samples = [[] for _ in range(NUM_HOURS)]
hourly_pending_samples = [[] for _ in range(NUM_HOURS)]
hourly_queue_samples = [[] for _ in range(NUM_HOURS)]

# Separate drain-period samples after 24 hours
drain_active_samples = []
drain_pending_samples = []
drain_queue_samples = []

step_debug_rows = []

# 3D queue storage:
# queue_lengths[tls_index][lane_type][time]
NUM_TLS = 4
NUM_LANES = 3
queue_lengths = [[[] for _ in range(NUM_LANES)] for _ in range(NUM_TLS)]

# -----------------------
# HELPERS
# -----------------------
def avg(values):
    return sum(values) / len(values) if values else 0


def compute_avg(values):
    return sum(values) / len(values) if values else None


def format_hour(hour):
    hour_12 = hour % 12
    if hour_12 == 0:
        hour_12 = 12
    suffix = "AM" if hour < 12 else "PM"
    return f"{hour_12}{suffix}"


# -----------------------
# SIMULATION LOOP
# -----------------------
while (
    traci.simulation.getTime() < MAX_SIM_TIME
    and (
        traci.simulation.getMinExpectedNumber() > 0
        or traci.simulation.getTime() < ROUTE_GENERATION_END
    )
):
    traci.simulationStep()
    t = traci.simulation.getTime()

    sim_hour = int(t // HOUR_SECONDS)
    current_hour = min(sim_hour, NUM_HOURS - 1)
    is_drain_period = t >= ROUTE_GENERATION_END

    active_vehicle_count = len(traci.vehicle.getIDList())
    expected_remaining = traci.simulation.getMinExpectedNumber()

    # -----------------------
    # Vehicles that just departed
    # -----------------------
    departed_this_step = traci.simulation.getDepartedIDList()

    for veh in departed_this_step:
        depart_time[veh] = t
        route_of[veh] = traci.vehicle.getRouteID(veh)
        last_waiting_time[veh] = 0.0

        dep_hour = int(t // HOUR_SECONDS)
        if 0 <= dep_hour < NUM_HOURS:
            hourly_departures[dep_hour] += 1

    # -----------------------
    # Update waiting times
    # -----------------------
    for veh in traci.vehicle.getIDList():
        last_waiting_time[veh] = traci.vehicle.getAccumulatedWaitingTime(veh)

    # -----------------------
    # Vehicles that just arrived
    # -----------------------
    arrived_this_step = traci.simulation.getArrivedIDList()

    for veh in arrived_this_step:
        if veh in depart_time:
            route = route_of[veh]
            dep_t = depart_time[veh]

            travel_time = t - dep_t
            waiting_time = last_waiting_time.get(veh, 0.0)

            # Bucket by departure hour, not arrival hour
            hour_index = int(dep_t // HOUR_SECONDS)

            if 0 <= hour_index < NUM_HOURS:
                travel_times[route].append(travel_time)
                waiting_times[route].append(waiting_time)
                throughput[route] += 1

                hourly_travel_times[hour_index].append(travel_time)
                hourly_waiting_times[hour_index].append(waiting_time)
                hourly_throughput[hour_index] += 1
                hourly_arrivals[hour_index] += 1

            depart_time.pop(veh, None)
            route_of.pop(veh, None)
            last_waiting_time.pop(veh, None)

    # -----------------------
    # QUEUE LENGTH PER TLS PER LANE
    # -----------------------
    for tls_index, tls in enumerate(TLS_ORDER):
        lanes = traci.trafficlight.getControlledLanes(tls)
        lanes = list(dict.fromkeys(lanes))  # remove duplicates

        # Assumes 3 lanes per incoming direction:
        # lane 0 = left
        # lane 1 = straight
        # lane 2 = right
        for lane_type in range(3):
            if lane_type < len(lanes):
                lane_id = lanes[lane_type]

                queue = 0
                for veh in traci.lane.getLastStepVehicleIDs(lane_id):
                    if traci.vehicle.getSpeed(veh) < 0.1:
                        queue += 1

                queue_lengths[tls_index][lane_type].append(queue)
            else:
                queue_lengths[tls_index][lane_type].append(0)

    # Total queue from most recent lane samples
    total_queue_now = 0

    for tls_index in range(NUM_TLS):
        for lane_type in range(NUM_LANES):
            if queue_lengths[tls_index][lane_type]:
                total_queue_now += queue_lengths[tls_index][lane_type][-1]

    # -----------------------
    # DEBUG SAMPLING EVERY 60 SECONDS
    # -----------------------
    if int(t) % 60 == 0:
        if 0 <= sim_hour < NUM_HOURS:
            hourly_active_samples[sim_hour].append(active_vehicle_count)
            hourly_pending_samples[sim_hour].append(expected_remaining)
            hourly_queue_samples[sim_hour].append(total_queue_now)
        else:
            drain_active_samples.append(active_vehicle_count)
            drain_pending_samples.append(expected_remaining)
            drain_queue_samples.append(total_queue_now)

        step_debug_rows.append(
            {
                "time": t,
                "sim_hour": sim_hour,
                "clamped_hour": current_hour,
                "is_drain_period": is_drain_period,
                "active_vehicles": active_vehicle_count,
                "min_expected_remaining": expected_remaining,
                "total_queue": total_queue_now,
                "departed_this_step": len(departed_this_step),
                "arrived_this_step": len(arrived_this_step),
                "departed_this_hour": hourly_departures[current_hour],
                "arrivals_bucketed_to_this_departure_hour": hourly_arrivals[current_hour],
                "throughput_bucketed_to_this_departure_hour": hourly_throughput[current_hour],
                "vehicles_still_tracked": len(depart_time),
            }
        )

traci.close()

# -----------------------
# SAVE DEBUG FILES
# -----------------------
hourly_debug_rows = []

for hour in range(NUM_HOURS):
    hourly_debug_rows.append(
        {
            "hour": hour,
            "hour_label": f"{format_hour(hour)} - {format_hour((hour + 1) % NUM_HOURS)}",
            "departures_actual": hourly_departures[hour],
            "arrivals_bucketed_by_departure_hour": hourly_arrivals[hour],
            "throughput_bucketed_by_departure_hour": hourly_throughput[hour],
            "unfinished_from_departure_hour": hourly_departures[hour] - hourly_arrivals[hour],
            "avg_active_vehicles_sampled": avg(hourly_active_samples[hour]),
            "max_active_vehicles_sampled": max(hourly_active_samples[hour])
            if hourly_active_samples[hour]
            else 0,
            "avg_min_expected_remaining_sampled": avg(hourly_pending_samples[hour]),
            "max_min_expected_remaining_sampled": max(hourly_pending_samples[hour])
            if hourly_pending_samples[hour]
            else 0,
            "avg_total_queue_sampled": avg(hourly_queue_samples[hour]),
            "max_total_queue_sampled": max(hourly_queue_samples[hour])
            if hourly_queue_samples[hour]
            else 0,
        }
    )

# Add one extra drain-period row for after 24 hours
hourly_debug_rows.append(
    {
        "hour": "drain",
        "hour_label": "After 24h drain period",
        "departures_actual": "",
        "arrivals_bucketed_by_departure_hour": "",
        "throughput_bucketed_by_departure_hour": "",
        "unfinished_from_departure_hour": sum(hourly_departures) - sum(hourly_arrivals),
        "avg_active_vehicles_sampled": avg(drain_active_samples),
        "max_active_vehicles_sampled": max(drain_active_samples)
        if drain_active_samples
        else 0,
        "avg_min_expected_remaining_sampled": avg(drain_pending_samples),
        "max_min_expected_remaining_sampled": max(drain_pending_samples)
        if drain_pending_samples
        else 0,
        "avg_total_queue_sampled": avg(drain_queue_samples),
        "max_total_queue_sampled": max(drain_queue_samples)
        if drain_queue_samples
        else 0,
    }
)

with HOURLY_DEBUG_CSV.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=hourly_debug_rows[0].keys())
    writer.writeheader()
    writer.writerows(hourly_debug_rows)

if step_debug_rows:
    with STEP_DEBUG_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=step_debug_rows[0].keys())
        writer.writeheader()
        writer.writerows(step_debug_rows)

# -----------------------
# RESULTS
# -----------------------
print("\n===== PERFORMANCE METRICS =====")
print("\nFIXED")

metrics_rows = []

for hour in range(NUM_HOURS):
    start_label = format_hour(hour)
    end_label = format_hour((hour + 1) % NUM_HOURS)
    avg_travel_time = compute_avg(hourly_travel_times[hour])
    avg_waiting_time = compute_avg(hourly_waiting_times[hour])

    metrics_rows.append(
        {
            "hour": hour,
            "hour_label": f"{start_label} - {end_label}",
            "throughput": hourly_throughput[hour],
            "average_travel_time": avg_travel_time,
            "average_waiting_time": avg_waiting_time,
            "departures_actual": hourly_departures[hour],
            "unfinished_from_departure_hour": hourly_departures[hour] - hourly_arrivals[hour],
        }
    )

    print(f"\nResults for {start_label} - {end_label}:")
    print(f"  Departures: {hourly_departures[hour]}")
    print(f"  Throughput: {hourly_throughput[hour]}")
    print(f"  Unfinished from this departure hour: {hourly_departures[hour] - hourly_arrivals[hour]}")

    print(
        f"  Average Travel Time: {avg_travel_time:.2f} s"
        if avg_travel_time is not None
        else "  Average Travel Time: N/A"
    )
    print(
        f"  Average Waiting Time: {avg_waiting_time:.2f} s"
        if avg_waiting_time is not None
        else "  Average Waiting Time: N/A"
    )

with METRICS_CSV.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=metrics_rows[0].keys())
    writer.writeheader()
    writer.writerows(metrics_rows)

print(f"\nSaved hourly metrics CSV to: {METRICS_CSV}")
print(f"Saved hourly debug CSV to: {HOURLY_DEBUG_CSV}")
print(f"Saved step debug CSV to: {STEP_DEBUG_CSV}")