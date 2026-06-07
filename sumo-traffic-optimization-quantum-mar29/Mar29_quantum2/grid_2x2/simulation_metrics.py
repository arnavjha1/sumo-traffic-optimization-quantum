import csv
from pathlib import Path

import traci

ROUTE_GENERATION_END = 86400
MAX_SIM_TIME = 100000
HOUR_SECONDS = 3600
NUM_HOURS = 24

PROCESS_OUTPUT_DIR = Path("data_analysis") / "simulation_process_data"
PROCESS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def start_sumo(sumo_binary, sumo_config, max_depart_delay=300):
    """Start SUMO with a bounded depart delay so excessive demand is easier to detect."""
    traci.start([
        sumo_binary,
        "-c",
        sumo_config,
        "--max-depart-delay",
        str(max_depart_delay),
    ])


def should_continue_simulation(route_generation_end=ROUTE_GENERATION_END, max_sim_time=MAX_SIM_TIME):
    """Run through the 24h route-generation window and then allow remaining vehicles to drain."""
    t = traci.simulation.getTime()
    return (
        t < max_sim_time
        and (
            traci.simulation.getMinExpectedNumber() > 0
            or t < route_generation_end
        )
    )


def format_hour(hour):
    hour_12 = hour % 12
    if hour_12 == 0:
        hour_12 = 12
    suffix = "AM" if hour < 12 else "PM"
    return f"{hour_12}{suffix}"


def avg(values):
    return sum(values) / len(values) if values else 0


def compute_avg(values):
    return sum(values) / len(values) if values else None


class PerformanceTracker:
    """
    Shared vehicle-level metric collector for fixed, queue, classical, and quantum runs.

    Important behavior:
    - Vehicle travel/waiting metrics are bucketed by DEPARTURE hour, not arrival hour.
    - The simulation may continue past 86400 seconds to drain vehicles, but metrics still
      count vehicles under their original departure hour.
    - Debug CSVs are written to data_analysis/simulation_process_data.
    """

    def __init__(self, controller_name, num_hours=NUM_HOURS, hour_seconds=HOUR_SECONDS):
        self.controller_name = controller_name.lower()
        self.controller_label = controller_name.upper()
        self.num_hours = num_hours
        self.hour_seconds = hour_seconds

        self.depart_time = {}
        self.route_of = {}
        self.last_waiting_time = {}

        self.travel_times = {}
        self.waiting_times = {}
        self.throughput = {}

        self.hourly_travel_times = [[] for _ in range(num_hours)]
        self.hourly_waiting_times = [[] for _ in range(num_hours)]
        self.hourly_throughput = [0 for _ in range(num_hours)]
        self.hourly_departures = [0 for _ in range(num_hours)]
        self.hourly_arrivals = [0 for _ in range(num_hours)]

        self.hourly_active_samples = [[] for _ in range(num_hours)]
        self.hourly_pending_samples = [[] for _ in range(num_hours)]
        self.hourly_queue_samples = [[] for _ in range(num_hours)]

        self.drain_active_samples = []
        self.drain_pending_samples = []
        self.drain_queue_samples = []

        self.step_debug_rows = []

    def process_vehicle_events(self):
        """Record departed vehicles, update waiting times, and collect arrivals."""
        t = traci.simulation.getTime()

        departed_this_step = traci.simulation.getDepartedIDList()
        for veh in departed_this_step:
            self.depart_time[veh] = t
            self.route_of[veh] = traci.vehicle.getRouteID(veh)
            self.last_waiting_time[veh] = 0.0

            dep_hour = int(t // self.hour_seconds)
            if 0 <= dep_hour < self.num_hours:
                self.hourly_departures[dep_hour] += 1

        for veh in traci.vehicle.getIDList():
            self.last_waiting_time[veh] = traci.vehicle.getAccumulatedWaitingTime(veh)

        arrived_this_step = traci.simulation.getArrivedIDList()
        for veh in arrived_this_step:
            if veh not in self.depart_time:
                continue

            route = self.route_of[veh]
            dep_t = self.depart_time[veh]
            travel_time = t - dep_t
            waiting_time = self.last_waiting_time.get(veh, 0.0)

            # Bucket by departure hour, not arrival hour.
            hour_index = int(dep_t // self.hour_seconds)
            if 0 <= hour_index < self.num_hours:
                self.travel_times.setdefault(route, []).append(travel_time)
                self.waiting_times.setdefault(route, []).append(waiting_time)
                self.throughput[route] = self.throughput.get(route, 0) + 1

                self.hourly_travel_times[hour_index].append(travel_time)
                self.hourly_waiting_times[hour_index].append(waiting_time)
                self.hourly_throughput[hour_index] += 1
                self.hourly_arrivals[hour_index] += 1

            self.depart_time.pop(veh, None)
            self.route_of.pop(veh, None)
            self.last_waiting_time.pop(veh, None)

        return len(departed_this_step), len(arrived_this_step)

    def sample_debug(self, total_queue_now, departed_this_step, arrived_this_step, route_generation_end=ROUTE_GENERATION_END):
        """Sample simulation-level debug data every 60 seconds."""
        t = traci.simulation.getTime()
        if int(t) % 60 != 0:
            return

        sim_hour = int(t // self.hour_seconds)
        current_hour = min(sim_hour, self.num_hours - 1)
        is_drain_period = t >= route_generation_end

        active_vehicle_count = len(traci.vehicle.getIDList())
        expected_remaining = traci.simulation.getMinExpectedNumber()

        if 0 <= sim_hour < self.num_hours:
            self.hourly_active_samples[sim_hour].append(active_vehicle_count)
            self.hourly_pending_samples[sim_hour].append(expected_remaining)
            self.hourly_queue_samples[sim_hour].append(total_queue_now)
        else:
            self.drain_active_samples.append(active_vehicle_count)
            self.drain_pending_samples.append(expected_remaining)
            self.drain_queue_samples.append(total_queue_now)

        self.step_debug_rows.append({
            "time": t,
            "sim_hour": sim_hour,
            "clamped_hour": current_hour,
            "is_drain_period": is_drain_period,
            "active_vehicles": active_vehicle_count,
            "min_expected_remaining": expected_remaining,
            "total_queue": total_queue_now,
            "departed_this_step": departed_this_step,
            "arrived_this_step": arrived_this_step,
            "departed_this_hour": self.hourly_departures[current_hour],
            "arrivals_bucketed_to_this_departure_hour": self.hourly_arrivals[current_hour],
            "throughput_bucketed_to_this_departure_hour": self.hourly_throughput[current_hour],
            "vehicles_still_tracked": len(self.depart_time),
        })

    def build_hourly_debug_rows(self):
        rows = []
        for hour in range(self.num_hours):
            rows.append({
                "hour": hour,
                "hour_label": f"{format_hour(hour)} - {format_hour((hour + 1) % self.num_hours)}",
                "departures_actual": self.hourly_departures[hour],
                "arrivals_bucketed_by_departure_hour": self.hourly_arrivals[hour],
                "throughput_bucketed_by_departure_hour": self.hourly_throughput[hour],
                "unfinished_from_departure_hour": self.hourly_departures[hour] - self.hourly_arrivals[hour],
                "avg_active_vehicles_sampled": avg(self.hourly_active_samples[hour]),
                "max_active_vehicles_sampled": max(self.hourly_active_samples[hour]) if self.hourly_active_samples[hour] else 0,
                "avg_min_expected_remaining_sampled": avg(self.hourly_pending_samples[hour]),
                "max_min_expected_remaining_sampled": max(self.hourly_pending_samples[hour]) if self.hourly_pending_samples[hour] else 0,
                "avg_total_queue_sampled": avg(self.hourly_queue_samples[hour]),
                "max_total_queue_sampled": max(self.hourly_queue_samples[hour]) if self.hourly_queue_samples[hour] else 0,
            })

        rows.append({
            "hour": "drain",
            "hour_label": "After 24h drain period",
            "departures_actual": "",
            "arrivals_bucketed_by_departure_hour": "",
            "throughput_bucketed_by_departure_hour": "",
            "unfinished_from_departure_hour": sum(self.hourly_departures) - sum(self.hourly_arrivals),
            "avg_active_vehicles_sampled": avg(self.drain_active_samples),
            "max_active_vehicles_sampled": max(self.drain_active_samples) if self.drain_active_samples else 0,
            "avg_min_expected_remaining_sampled": avg(self.drain_pending_samples),
            "max_min_expected_remaining_sampled": max(self.drain_pending_samples) if self.drain_pending_samples else 0,
            "avg_total_queue_sampled": avg(self.drain_queue_samples),
            "max_total_queue_sampled": max(self.drain_queue_samples) if self.drain_queue_samples else 0,
        })
        return rows

    def build_metrics_rows(self):
        rows = []
        for hour in range(self.num_hours):
            start_label = format_hour(hour)
            end_label = format_hour((hour + 1) % self.num_hours)
            avg_travel_time = compute_avg(self.hourly_travel_times[hour])
            avg_waiting_time = compute_avg(self.hourly_waiting_times[hour])
            rows.append({
                "hour": hour,
                "hour_label": f"{start_label} - {end_label}",
                "throughput": self.hourly_throughput[hour],
                "average_travel_time": avg_travel_time,
                "average_waiting_time": avg_waiting_time,
                "departures_actual": self.hourly_departures[hour],
                "unfinished_from_departure_hour": self.hourly_departures[hour] - self.hourly_arrivals[hour],
            })
        return rows

    def save_csvs(self):
        hourly_debug_rows = self.build_hourly_debug_rows()
        metrics_rows = self.build_metrics_rows()

        hourly_debug_csv = PROCESS_OUTPUT_DIR / f"{self.controller_name}_hourly_debug.csv"
        step_debug_csv = PROCESS_OUTPUT_DIR / f"{self.controller_name}_step_debug.csv"
        metrics_csv = PROCESS_OUTPUT_DIR / f"{self.controller_name}_hourly_metrics.csv"

        with hourly_debug_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=hourly_debug_rows[0].keys())
            writer.writeheader()
            writer.writerows(hourly_debug_rows)

        if self.step_debug_rows:
            with step_debug_csv.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=self.step_debug_rows[0].keys())
                writer.writeheader()
                writer.writerows(self.step_debug_rows)

        with metrics_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=metrics_rows[0].keys())
            writer.writeheader()
            writer.writerows(metrics_rows)

        return metrics_csv, hourly_debug_csv, step_debug_csv

    def print_results(self):
        print("\n===== PERFORMANCE METRICS =====")
        print(f"\n{self.controller_label}")

        for hour in range(self.num_hours):
            start_label = format_hour(hour)
            end_label = format_hour((hour + 1) % self.num_hours)
            avg_travel_time = compute_avg(self.hourly_travel_times[hour])
            avg_waiting_time = compute_avg(self.hourly_waiting_times[hour])

            print(f"\nResults for {start_label} - {end_label}:")
            print(f"  Departures: {self.hourly_departures[hour]}")
            print(f"  Throughput: {self.hourly_throughput[hour]}")
            print(f"  Unfinished from this departure hour: {self.hourly_departures[hour] - self.hourly_arrivals[hour]}")
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

    def save_and_print(self):
        self.print_results()
        metrics_csv, hourly_debug_csv, step_debug_csv = self.save_csvs()
        print(f"\nSaved hourly metrics CSV to: {metrics_csv}")
        print(f"Saved hourly debug CSV to: {hourly_debug_csv}")
        print(f"Saved step debug CSV to: {step_debug_csv}")


def collect_queue_lengths_4d(tls_order, num_sides, num_lanes, queue_lengths, regular_cars=None, halted_speed=0.1):
    """
    Collect per-TLS, per-side, per-lane queue lengths.

    This intentionally preserves the 4D structure used by the queue, classical,
    and quantum controllers:
        queue_lengths[tls_index][side_index][lane_index][time]

    If regular_cars is provided, moving vehicle counts are collected with the same
    indexing structure for pressure calculations.
    """
    total_queue_now = 0

    for tls_index, tls in enumerate(tls_order):
        lanes = traci.trafficlight.getControlledLanes(tls)
        lanes = list(dict.fromkeys(lanes))

        lanes_per_side = len(lanes) // num_sides if num_sides else 0

        for side_index in range(num_sides):
            for lane_index in range(num_lanes):
                lane_pos = side_index * lanes_per_side + lane_index

                if lane_pos < len(lanes):
                    lane_id = lanes[lane_pos]
                    veh_ids = traci.lane.getLastStepVehicleIDs(lane_id)
                    queue = sum(1 for veh in veh_ids if traci.vehicle.getSpeed(veh) < halted_speed)
                    moving = sum(1 for veh in veh_ids if traci.vehicle.getSpeed(veh) >= halted_speed)
                else:
                    queue = 0
                    moving = 0

                queue_lengths[tls_index][side_index][lane_index].append(queue)
                total_queue_now += queue

                if regular_cars is not None:
                    regular_cars[tls_index][side_index][lane_index].append(moving)

    return total_queue_now
