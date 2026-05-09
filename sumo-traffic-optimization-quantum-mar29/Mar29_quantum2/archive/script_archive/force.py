import xml.etree.ElementTree as ET

tree = ET.parse("test_grid.net.xml")
root = tree.getroot()

count = 0
for j in root.findall("junction"):
    jtype = j.get("type")
    if jtype not in ("dead_end", "internal"):
        j.set("type", "traffic_light")
        count += 1

print("Converted junctions to traffic lights:", count)

tree.write("test_grid_all_tls.net.xml", encoding="utf-8", xml_declaration=True)
