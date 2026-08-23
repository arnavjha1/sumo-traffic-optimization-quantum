import subprocess
import sys
import xml.etree.ElementTree as ET
import pandas as pd
import numpy as np
from pathlib import Path

# Paths
BASE_DIR = Path("data_analysis")
ALPHA_SCRIPT = BASE_DIR / "calc_alpha.py"
TRAFFIC_SCRIPT = BASE_DIR / "calc_traffic_over_time.py"
ROUTE_PROBABILITY_SCRIPT = BASE_DIR / "route_probability_gen_3x3.py"

ALPHA_SUMMARY_CSV = BASE_DIR / "generated_data" / "alpha_citywide_summary.csv"
HOURLY_CONSTANTS_CSV = BASE_DIR / "generated_data" / "calculated_hourly_constants.csv"
ROUTE_PROBABILITIES_CSV = BASE_DIR / "generated_data" / "generated_route_probabilities_3x3.csv"

ROUTES_OUTPUT_XML = Path("grid_3x3/routes_3x3") / "routes3x3_data.rou.xml"

# Debug/process output folder
PROCESS_OUTPUT_DIR = BASE_DIR / "simulation_process_data"
PROCESS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Scale demand down to avoid oversaturating the 2x2 network.
DEMAND_SCALE = 0.45

# 1. Run scripts and wait for completion
subprocess.run([sys.executable, str(ALPHA_SCRIPT)], check=True)
subprocess.run([sys.executable, str(ROUTE_PROBABILITY_SCRIPT)], check=True)

try:
    traffic_result = subprocess.run(
        [sys.executable, str(TRAFFIC_SCRIPT)],
        check=True,
        capture_output=True,
        text=True,
    )
    print(traffic_result.stdout, end="")
    print(traffic_result.stderr, end="", file=sys.stderr)
except subprocess.CalledProcessError as exc:
    if not HOURLY_CONSTANTS_CSV.exists():
        print(exc.stdout, end="")
        print(exc.stderr, end="", file=sys.stderr)
        raise

    print(
        f"Warning: {TRAFFIC_SCRIPT} failed. "
        f"Using existing hourly constants CSV: {HOURLY_CONSTANTS_CSV}"
    )

# 2. Load outputs
alpha_summary = pd.read_csv(ALPHA_SUMMARY_CSV)
hourly_constants = pd.read_csv(HOURLY_CONSTANTS_CSV)
route_probabilities = pd.read_csv(ROUTE_PROBABILITIES_CSV)

# 3. Extract needed values
alpha_straight = float(alpha_summary["mean_alpha_straight"].iloc[0])
alpha_left = float(alpha_summary["mean_alpha_left"].iloc[0])
alpha_right = float(alpha_summary["mean_alpha_right"].iloc[0])
departure_constant = alpha_left + alpha_right

hour_constant_list = hourly_constants["hour_constant"].tolist()
average_hour_traffic_list = hourly_constants["average_hourly_traffic"].tolist()

# 4. Build 24x3 array: [hourly_rate, alpha_straight, departure_constant]
data_array = np.zeros((24, 3))

for i in range(24):
    # This is the base vehicles/hour entering EACH outside inflow branch before scaling.
    data_array[i, 0] = average_hour_traffic_list[i] * hour_constant_list[i] * 24
    data_array[i, 1] = alpha_straight
    data_array[i, 2] = departure_constant

df_24x3 = pd.DataFrame(
    data_array,
    columns=["base_hourly_rate_per_entry", "alpha_straight", "departure_constant"],
)

df_24x3["demand_scale"] = DEMAND_SCALE
df_24x3["scaled_hourly_rate_per_entry"] = (
    df_24x3["base_hourly_rate_per_entry"] * DEMAND_SCALE
)
df_24x3["scaled_total_network_vph_expected"] = (
    df_24x3["scaled_hourly_rate_per_entry"] * 8
)

print("\nHourly demand table:")
print(df_24x3)

hourly_demand_path = PROCESS_OUTPUT_DIR / "route_generation_hourly_demand.csv"
df_24x3.to_csv(hourly_demand_path, index=False)

# 5. Build 72x2 array: [route_edges, normalized_probability]
route_probability_array = route_probabilities[
    ["route_edges", "normalized_probability"]
].to_numpy(dtype=object)

df_72x2 = pd.DataFrame(
    route_probability_array,
    columns=["route_tiles", "normalized_probability"],
)

print("\nRoute probability table:")
print(df_72x2)

# 6. Write route XML with 72 routes and 24 hourly flows per route
routes_root = ET.Element("routes")

ET.SubElement(
    routes_root,
    "vType",
    {
        "id": "car",
        "accel": "2.6",
        "decel": "4.5",
        "maxSpeed": "13.9",
        "length": "5",
    },
)

for _, route in route_probabilities.iterrows():
    ET.SubElement(
        routes_root,
        "route",
        {
            "id": str(route["route_id"]),
            "edges": str(route["route_edges"]),
        },
    )

validation_rows = []

for hour in range(24):
    base_hourly_rate = data_array[hour, 0]
    scaled_hourly_rate = base_hourly_rate * DEMAND_SCALE

    for _, route in route_probabilities.iterrows():
        route_id = str(route["route_id"])
        route_edges = str(route["route_edges"])
        start_edge = str(route["start_edge"]) if "start_edge" in route else route_edges.split()[0]
        route_probability = float(route["normalized_probability"])

        begin = hour * 3600
        end = (hour + 1) * 3600

        vehs_per_hour = scaled_hourly_rate * route_probability

        validation_rows.append(
            {
                "hour": hour,
                "begin": begin,
                "end": end,
                "route_id": route_id,
                "start_edge": start_edge,
                "route_edges": route_edges,
                "route_probability": route_probability,
                "base_hourly_rate_per_entry": base_hourly_rate,
                "demand_scale": DEMAND_SCALE,
                "scaled_hourly_rate_per_entry": scaled_hourly_rate,
                "vehs_per_hour": vehs_per_hour,
            }
        )

        ET.SubElement(
            routes_root,
            "flow",
            {
                "id": f"{route_id}_h{hour}",
                "type": "car",
                "route": route_id,
                "begin": str(begin),
                "end": str(end),
                "vehsPerHour": f"{vehs_per_hour:.6f}",
            },
        )

ET.indent(routes_root, space="    ")

ROUTES_OUTPUT_XML.parent.mkdir(parents=True, exist_ok=True)
ET.ElementTree(routes_root).write(
    ROUTES_OUTPUT_XML,
    encoding="unicode",
    xml_declaration=False,
)

with ROUTES_OUTPUT_XML.open("a", encoding="utf-8") as route_file:
    route_file.write("\n")

# 7. Save validation outputs
validation_df = pd.DataFrame(validation_rows)

validation_path = PROCESS_OUTPUT_DIR / "route_generation_validation.csv"
validation_df.to_csv(validation_path, index=False)

hourly_validation = validation_df.groupby("hour").agg(
    total_network_vph=("vehs_per_hour", "sum"),
    max_route_vph=("vehs_per_hour", "max"),
    min_route_vph=("vehs_per_hour", "min"),
    route_count=("route_id", "count"),
    unique_start_edges=("start_edge", "nunique"),
    base_hourly_rate_per_entry=("base_hourly_rate_per_entry", "first"),
    scaled_hourly_rate_per_entry=("scaled_hourly_rate_per_entry", "first"),
    demand_scale=("demand_scale", "first"),
).reset_index()

hourly_validation_path = PROCESS_OUTPUT_DIR / "route_generation_hourly_summary.csv"
hourly_validation.to_csv(hourly_validation_path, index=False)

start_edge_validation = validation_df.groupby(["hour", "start_edge"]).agg(
    start_edge_vph=("vehs_per_hour", "sum"),
    route_probability_sum=("route_probability", "sum"),
    route_count=("route_id", "count"),
).reset_index()

start_edge_validation_path = PROCESS_OUTPUT_DIR / "route_generation_start_edge_summary.csv"
start_edge_validation.to_csv(start_edge_validation_path, index=False)

print("\nRoute generation hourly summary:")
print(hourly_validation)

print(f"\nSaved route XML to: {ROUTES_OUTPUT_XML}")
print(f"Saved hourly demand table to: {hourly_demand_path}")
print(f"Saved route validation to: {validation_path}")
print(f"Saved hourly route summary to: {hourly_validation_path}")
print(f"Saved start-edge route summary to: {start_edge_validation_path}")