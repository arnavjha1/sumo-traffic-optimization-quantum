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
ROUTE_PROBABILITY_SCRIPT = BASE_DIR / "route_probability_gen.py"
ALPHA_SUMMARY_CSV = BASE_DIR / "generated_data" / "alpha_citywide_summary.csv"
HOURLY_CONSTANTS_CSV = BASE_DIR / "generated_data" / "calculated_hourly_constants.csv"
ROUTE_PROBABILITIES_CSV = BASE_DIR / "generated_data" / "generated_route_probabilities.csv"
ROUTES_OUTPUT_XML = Path("routes_2x2") / "routes2x2_data.rou.xml"

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
alpha_straight = alpha_summary["mean_alpha_straight"].iloc[0]
alpha_left = alpha_summary["mean_alpha_left"].iloc[0]
alpha_right = alpha_summary["mean_alpha_right"].iloc[0]
departure_constant = alpha_left + alpha_right

hour_constant_list = hourly_constants["hour_constant"].tolist()
average_hour_traffic_list = hourly_constants["average_hourly_traffic"].tolist()

# 4. Build 24x4 array: [average_hour_traffic, hour_constant, alpha_straight, departure_constant]
data_array = np.zeros((24, 3))

for i in range(24):
    data_array[i, 0] = average_hour_traffic_list[i] * hour_constant_list[i] * 24
    data_array[i, 1] = alpha_straight
    data_array[i, 2] = departure_constant

# Optional: convert to pandas DataFrame for easier inspection
df_24x3 = pd.DataFrame(
    data_array,
    columns=["hourly_rate", "alpha_straight", "departure_constant"]
)

print(df_24x3)

# 5. Build 72x2 array: [route_edges, normalized_probability]
route_probability_array = route_probabilities[
    ["route_edges", "normalized_probability"]
].to_numpy(dtype=object)

df_72x2 = pd.DataFrame(
    route_probability_array,
    columns=["route_tiles", "normalized_probability"]
)

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

for hour in range(24):
    for _, route in route_probabilities.iterrows():
        route_id = str(route["route_id"])
        route_probability = float(route["normalized_probability"])
        begin = hour * 3600
        end = (hour + 1) * 3600
        vehs_per_hour = data_array[hour, 0] * route_probability

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

print(f"Saved route XML to: {ROUTES_OUTPUT_XML}")
