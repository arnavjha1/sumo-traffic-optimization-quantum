import xml.etree.ElementTree as ET

# Input / output files
input_file = "test_grid_FORCED_TLS.net.xml"
output_file = "test_grid_FORCED_TLS_FIXED.net.xml"

# Load XML
tree = ET.parse(input_file)
root = tree.getroot()

# --- Step 1: Collect all junction IDs that are traffic lights ---
tl_junctions = {}
for junction in root.findall('junction'):
    if junction.attrib.get('type') == 'traffic_light':
        tl_junctions[junction.attrib['id']] = {
            'junction': junction,
            'link_count': 0  # we'll count outgoing lanes
        }

# --- Step 2: Fix connections ---
for connection in root.findall('connection'):
    tl_id = connection.attrib.get('tl')
    if tl_id in tl_junctions:
        # assign sequential linkIndex for this junction
        connection.attrib['linkIndex'] = str(tl_junctions[tl_id]['link_count'])
        tl_junctions[tl_id]['link_count'] += 1
        # ensure state attribute exists
        connection.attrib['state'] = 'o'

# --- Step 3: Add tlLogic blocks if missing ---
for tl_id, info in tl_junctions.items():
    # Check if tlLogic already exists
    existing = root.find(f"tlLogic[@id='{tl_id}']")
    if existing is not None:
        continue  # already there
    
    # Create simple 2-phase program: NS / EW
    tl_logic = ET.Element('tlLogic', id=tl_id, type="static", programID="0", offset="0")
    # All lanes default to green/red in phases
    link_count = info['link_count']
    # Simple NS green / EW red
    phase1 = ET.Element('phase', duration="30", state="G" * (link_count // 2) + "r" * (link_count - link_count // 2))
    # Simple yellow transition
    phase2 = ET.Element('phase', duration="3", state="y" * link_count)
    # EW green / NS red
    phase3 = ET.Element('phase', duration="30", state="r" * (link_count // 2) + "G" * (link_count - link_count // 2))
    # Yellow again
    phase4 = ET.Element('phase', duration="3", state="y" * link_count)

    tl_logic.extend([phase1, phase2, phase3, phase4])
    root.append(tl_logic)

# --- Step 4: Write new network ---
tree.write(output_file, encoding='utf-8', xml_declaration=True)
print(f"Fixed network saved to {output_file}")
