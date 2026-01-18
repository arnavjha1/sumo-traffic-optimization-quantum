import xml.etree.ElementTree as ET
from collections import defaultdict

print("SCRIPT STARTED")

INPUT = "test_grid.net.xml"
OUTPUT = "test_grid_FORCED_TLS.net.xml"

tree = ET.parse(INPUT)
root = tree.getroot()

# group connections by junction using the via edge
junction_connections = defaultdict(list)

for conn in root.findall("connection"):
    via = conn.get("via")
    if via and via.startswith(":"):
        junction_id = via.split("_")[0][1:]  # ":AB44_12_0" -> "AB44"
        junction_connections[junction_id].append(conn)

# apply tl + linkIndex + state
for junction_id, conns in junction_connections.items():
    for i, conn in enumerate(conns):
        conn.set("tl", junction_id)
        conn.set("linkIndex", str(i))
        conn.set("state", "o")

# add tlLogic blocks if missing
existing_tls = {tl.get("id") for tl in root.findall("tlLogic")}

for junction_id, conns in junction_connections.items():
    if junction_id in existing_tls:
        continue

    states = "o" * len(conns)

    tl = ET.SubElement(root, "tlLogic", {
        "id": junction_id,
        "type": "static",
        "programID": "0",
        "offset": "0"
    })

    ET.SubElement(tl, "phase", {
        "duration": "30",
        "state": states
    })

tree.write(OUTPUT, encoding="utf-8", xml_declaration=True)

print(f"Forced TLS on {len(junction_connections)} junctions")
