import xml.etree.ElementTree as ET

tree = ET.parse("grid.net.xml")
root = tree.getroot()

tls_count = 0

for junction in root.findall("junction"):
    if junction.get("type") not in ("dead_end", "internal"):
        junction.set("type", "traffic_light")
        tls_count += 1

print(f"Converted {tls_count} junctions to traffic lights")

tree.write("grid_tls.net.xml", encoding="utf-8", xml_declaration=True)
