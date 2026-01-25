import xml.etree.ElementTree as ET
from collections import defaultdict

INPUT_NET = "test_grid_FORCED_TLS_FIXED.net.xml"
OUTPUT_NET = "grid_tls_fixed.net.xml"

tree = ET.parse(INPUT_NET)
root = tree.getroot()

# SUMO namespaces (important)
ns = {"sumo": root.tag.split("}")[0].strip("{")}

# Collect all nodes that should be traffic lights
tls_nodes = set()
for node in root.findall("node"):
    if node.get("type") == "traffic_light":
        tls_nodes.add(node.get("id"))

# Collect connections by traffic light
connections_by_tls = defaultdict(list)

for conn in root.findall("connection"):
    via = conn.get("via")
    if not via:
        continue

    # via looks like ":AB44_12_0" → extract node ID
    tls_id = via.split("_")[0].replace(":", "")

    if tls_id in tls_nodes:
        connections_by_tls[tls_id].append(conn)

# Remove ALL existing tls attributes (clean slate)
for conn in root.findall("connection"):
    for attr in ["tl", "linkIndex", "state"]:
        if attr in conn.attrib:
            del conn.attrib[attr]

# Reassign connections correctly
for tls_id, conns in connections_by_tls.items():
    for idx, conn in enumerate(conns):
        conn.set("tl", tls_id)
        conn.set("linkIndex", str(idx))
        conn.set("state", "o")  # all off initially

# Write fixed net file
tree.write(OUTPUT_NET, encoding="utf-8", xml_declaration=True)

print(f"✅ Regenerated TLS connections written to {OUTPUT_NET}")
