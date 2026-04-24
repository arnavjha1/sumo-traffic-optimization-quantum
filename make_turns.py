import xml.etree.ElementTree as ET
from collections import defaultdict

NET_FILE = "grid_5x5/grid5x5_tls.net.xml"
OUTPUT_FILE = "grid_5x5/turns.xml"

# Parse network
tree = ET.parse(NET_FILE)
root = tree.getroot()

# Collect connections: fromEdge -> list of toEdges
connections = defaultdict(list)

for conn in root.findall("connection"):
    from_edge = conn.get("from")
    to_edge = conn.get("to")
    if from_edge and to_edge:
        connections[from_edge].append(to_edge)

# Build turns.xml
turns = ET.Element("turns")
interval = ET.SubElement(turns, "interval", begin="0", end="3600")

for from_edge, to_edges in connections.items():
    # Remove duplicates
    to_edges = list(set(to_edges))

    fe = ET.SubElement(interval, "fromEdge", id=from_edge)

    n = len(to_edges)

    # Assign probabilities
    if n == 3:
        probs = [0.2, 0.6, 0.2]  # left, straight, right (order arbitrary)
    else:
        # fallback: equal distribution
        probs = [1.0 / n] * n

    for to_edge, p in zip(to_edges, probs):
        ET.SubElement(fe, "toEdge", id=to_edge, probability=str(round(p, 3)))

# Write file
ET.ElementTree(turns).write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)

print(f"turns.xml generated at {OUTPUT_FILE}")