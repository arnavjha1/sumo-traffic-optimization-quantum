import xml.etree.ElementTree as ET
import pandas as pd
from pathlib import Path

# 10 min saturated test specific constants
SIM_DURATION = 600
ENTRY_VPH = 5000
ALPHA_INDEX = 5

# Paths
BASE_DIR = Path("data_route_gen_3x3")
ROUTE_PROBABILITY_SCRIPT = BASE_DIR / "route_probability_gen_3x3.py"
ROUTE_PROBABILITIES_CSV = BASE_DIR / "generated_data" / f"generated_route_probabilities_3x3_a{ALPHA_INDEX}.csv"
ROUTES_OUTPUT_XML = Path("grid_3x3/routes_3x3") / f"routes3x3_a{ALPHA_INDEX}.rou.xml"

# Debug/process output folder
# PROCESS_OUTPUT_DIR = BASE_DIR / "simulation_process_data"
# PROCESS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 1. Load generated probabilities
route_probabilities = pd.read_csv(ROUTE_PROBABILITIES_CSV)

print("\n===== 3x3 ROUTE INPUT CHECK =====")
print(f"Total routes loaded: {len(route_probabilities)}")
print(f"Unique start edges: {route_probabilities['start_edge'].nunique()}")

print("\nRoutes per start edge:")
print(route_probabilities.groupby("start_edge").size())

print("\nProbability sum per start edge:")
print(
    route_probabilities.groupby("start_edge")[
        "normalized_probability"
    ].sum()
)

print("===== END 3x3 ROUTE INPUT CHECK =====\n")


# 2. Build route probability table: [route_edges, normalized_probability]
route_probability_array = route_probabilities[
    ["route_edges", "normalized_probability"]
].to_numpy(dtype=object)

df_routes = pd.DataFrame(
    route_probability_array,
    columns=["route_tiles", "normalized_probability"],
)

print("\nRoute probability table:")
print(df_routes)


# 3. Write route XML with generated routes and one 600-second flow per route
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

# 4. Add one 600-second flow for every route
validation_rows = []

for _, route in route_probabilities.iterrows():
    route_id = str(route["route_id"])
    route_edges = str(route["route_edges"])
    start_edge = str(route["start_edge"])
    route_probability = float(route["normalized_probability"])

    vehs_per_hour = ENTRY_VPH * route_probability

    validation_rows.append(
        {
            "route_id": route_id,
            "start_edge": start_edge,
            "route_edges": route_edges,
            "route_probability": route_probability,
            "vehs_per_hour": vehs_per_hour,
        }
    )

    ET.SubElement(
        routes_root,
        "flow",
        {
            "id": f"flow_{route_id}",
            "type": "car",
            "route": route_id,
            "begin": "0",
            "end": str(SIM_DURATION),
            "vehsPerHour": f"{vehs_per_hour:.6f}",
        },
    )

# 5. create route xml
ET.indent(routes_root, space="    ")

ROUTES_OUTPUT_XML.parent.mkdir(parents=True, exist_ok=True)
ET.ElementTree(routes_root).write(
    ROUTES_OUTPUT_XML,
    encoding="unicode",
    xml_declaration=False,
)

with ROUTES_OUTPUT_XML.open("a", encoding="utf-8") as route_file:
    route_file.write("\n")

print(f"\nSaved route XML to: {ROUTES_OUTPUT_XML}")

# 6. validation
validation_df = pd.DataFrame(validation_rows)

start_edge_validation = (
    validation_df
    .groupby("start_edge")
    .agg(
        total_vph=("vehs_per_hour", "sum"),
        probability_sum=("route_probability", "sum"),
        route_count=("route_id", "count"),
    )
    .reset_index()
)

print("\n===== 600s FLOW VALIDATION =====")
print(start_edge_validation)

print("\nTotal network demand:")
print(f"{validation_df['vehs_per_hour'].sum():.2f} veh/h")

print("===== END 600s FLOW VALIDATION =====")