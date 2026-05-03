from unittest import result
import xml.etree.ElementTree as ET
from xml.dom import minidom


def generate_routes_xml(file_path, v_low, v_mid, v_high):
    # Helper to prettify XML
    def prettify(elem):
        rough_string = ET.tostring(elem, 'utf-8')
        reparsed = minidom.parseString(rough_string)
        return reparsed.toprettyxml(indent="    ")

    root = ET.Element("routes")

    # Vehicle type
    ET.SubElement(root, "vType", {
        "id": "car",
        "accel": "2.6",
        "decel": "4.5",
        "maxSpeed": "13.9",
        "length": "5"
    })

    # Parameters
    params = ET.SubElement(root, "parameters")
    ET.SubElement(params, "prob", {"id": "ALPHA", "value": "0.6"})
    ET.SubElement(params, "prob", {"id": "BETA", "value": "0.25"})
    ET.SubElement(params, "prob", {"id": "GAMMA", "value": "0.15"})

    # --- ROUTES ---
    routes_data = [
        ("r0", "-E7 E6"), ("r1", "-E7 A1B1 E0"), ("r2", "-E7 A1B1 E1"),
        ("r3", "-E7 A1B1 B1B0 E2"), ("r4", "-E7 A1A0 E5"),
        ("r5", "-E7 A1A0 E3"), ("r6", "-E7 A1A0 A0B0 E4"),
        ("r7", "-E6 E7"), ("r8", "-E6 A1A0 E5"),
        ("r9", "-E6 A1A0 E3"), ("r10", "-E6 A1A0 A0B0 E4"),
        ("r11", "-E6 A1B1 E0"), ("r12", "-E6 A1B1 E1"),
        ("r13", "-E6 A1B1 B1B0 E2"),
        ("r14", "-E1 E0"), ("r15", "-E1 B1A1 E6"),
        ("r16", "-E1 B1A1 E7"), ("r17", "-E1 B1A1 A1A0 E3"),
        ("r18", "-E1 B1B0 E4"), ("r19", "-E1 B1B0 E2"),
        ("r20", "-E1 B1B0 B0A0 E5"),
        ("r21", "-E0 E1"), ("r22", "-E0 B1B0 E4"),
        ("r23", "-E0 B1B0 E2"), ("r24", "-E0 B1B0 B0A0 E5"),
        ("r25", "-E0 B1A1 E6"), ("r26", "-E0 B1A1 E7"),
        ("r27", "-E0 B1A1 A1A0 E3"),
        ("r28", "-E5 E3"), ("r29", "-E5 A0B0 E2"),
        ("r30", "-E5 A0B0 E4"), ("r31", "-E5 A0B0 B0B1 E0"),
        ("r32", "-E5 A0A1 E7"), ("r33", "-E5 A0A1 E6"),
        ("r34", "-E5 A0A1 A1B1 E1"),
        ("r35", "-E3 E5"), ("r36", "-E3 A0A1 E7"),
        ("r37", "-E3 A0A1 E6"), ("r38", "-E3 A0A1 A1B1 E1"),
        ("r39", "-E3 A0B0 E2"), ("r40", "-E3 A0B0 E4"),
        ("r41", "-E3 A0B0 B0B1 E0"),
        ("r42", "-E4 E2"), ("r43", "-E4 B0A0 E3"),
        ("r44", "-E4 B0A0 E5"), ("r45", "-E4 B0A0 A0A1 E6"),
        ("r46", "-E4 B0B1 E1"), ("r47", "-E4 B0B1 E0"),
        ("r48", "-E4 B0B1 B1A1 E7"),
        ("r49", "-E2 E4"), ("r50", "-E2 B0B1 E1"),
        ("r51", "-E2 B0B1 E0"), ("r52", "-E2 B0B1 B1A1 E7"),
        ("r53", "-E2 B0A0 E3"), ("r54", "-E2 B0A0 E5"),
        ("r55", "-E2 B0A0 A0A1 E6")
    ]

    for rid, edges in routes_data:
        ET.SubElement(root, "route", {"id": rid, "edges": edges})

    # --- FLOW PATTERN ---
    # Pattern repeats every 7 flows
    pattern = [v_low, v_mid, v_high, v_mid, v_low, v_mid, v_low]

    flow_id = 0
    route_index = 0

    while route_index < len(routes_data):
        for val in pattern:
            if route_index >= len(routes_data):
                break

            ET.SubElement(root, "flow", {
                "id": f"flow{flow_id}",
                "type": "car",
                "route": routes_data[route_index][0],
                "begin": "0",
                "end": "600",
                "vehsPerHour": str(val)
            })

            flow_id += 1
            route_index += 1

    # Write file
    xml_str = prettify(root)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(xml_str)

file_path = "routes_2x2/routes2x2.rou.xml"

#=========================
# RUNNING SIMULATIONS
#=========================

import subprocess

NUM_TRAFFIC = 5
traffic_counts = [1000, 2000, 3000, 4000, 5000]
travel_times = [[],[],[],[]]
waiting_times = [[],[],[],[]]
throughputs = [[],[],[],[]]

for i in range(len(traffic_counts)):
    V_LOW = 324 * traffic_counts[i] / 5000
    V_MID = 755 * traffic_counts[i] / 5000
    V_HIGH = 1763 * traffic_counts[i] / 5000

    generate_routes_xml(file_path, V_LOW, V_MID, V_HIGH)

    # Run and wait for it to finish
    result = subprocess.run(["python", "grid_2x2/0_fixed.py"], capture_output=True, text=True)
    
    line = result.stdout.strip()
    data = [float(x) for x in line.split(',')]
    travel_times[0].append(data[0])
    waiting_times[0].append(data[1])
    throughputs[0].append(data[2])
    print("0-fixed: ", i)

for i in range(len(traffic_counts)):
    V_LOW = 324 * traffic_counts[i] / 5000
    V_MID = 755 * traffic_counts[i] / 5000
    V_HIGH = 1763 * traffic_counts[i] / 5000

    generate_routes_xml(file_path, V_LOW, V_MID, V_HIGH)

    # Run and wait for it to finish
    result = subprocess.run(["python", "grid_2x2/1_queue.py"], capture_output=True, text=True)
    line = result.stdout.strip()
    data = [float(x) for x in line.split(',') if x.strip() != '']
    travel_times[1].append(data[0])
    waiting_times[1].append(data[1])
    throughputs[1].append(data[2])
    print("1-queue: ", i)

for i in range(len(traffic_counts)):
    V_LOW = 324 * traffic_counts[i] / 5000
    V_MID = 755 * traffic_counts[i] / 5000
    V_HIGH = 1763 * traffic_counts[i] / 5000

    generate_routes_xml(file_path, V_LOW, V_MID, V_HIGH)

    # Run and wait for it to finish
    result = subprocess.run(["python", "grid_2x2/2_classical.py"], capture_output=True, text=True)
    
    line = result.stdout.strip()
    data = [float(x) for x in line.split(',')]
    travel_times[2].append(data[0])
    waiting_times[2].append(data[1])
    throughputs[2].append(data[2])
    print("2-classical: ", i)

for i in range(len(traffic_counts)):
    V_LOW = 324 * traffic_counts[i] / 5000
    V_MID = 755 * traffic_counts[i] / 5000
    V_HIGH = 1763 * traffic_counts[i] / 5000

    generate_routes_xml(file_path, V_LOW, V_MID, V_HIGH)

    # Run and wait for it to finish
    result = subprocess.run(["python", "grid_2x2/3_quantum.py"], capture_output=True, text=True)
    
    line = result.stdout.strip()
    data = [float(x) for x in line.split(',')]
    travel_times[3].append(data[0])
    waiting_times[3].append(data[1])
    throughputs[3].append(data[2])
    print("3-quantum: ", i)

print("Travel times:", travel_times)
print("Waiting times:", waiting_times)
print("Throughputs:", throughputs)

#=========================
# MAKE GRAPHS
#=========================

# Travel Time
import matplotlib.pyplot as plt
from scipy.interpolate import make_interp_spline
import numpy as np

alpha_smooth = np.linspace(min(traffic_counts), max(traffic_counts), 1000)

fixed_smooth = make_interp_spline(traffic_counts, travel_times[0])(alpha_smooth)
queue_smooth = make_interp_spline(traffic_counts, travel_times[1])(alpha_smooth)
classical_smooth = make_interp_spline(traffic_counts, travel_times[2])(alpha_smooth)
quantum_smooth = make_interp_spline(traffic_counts, travel_times[3])(alpha_smooth)

plt.figure()

plt.plot(alpha_smooth, fixed_smooth, linewidth=2.5, label='Fixed')
plt.plot(alpha_smooth, queue_smooth, linewidth=2.5, label='Queue')
plt.plot(alpha_smooth, classical_smooth, linewidth=2.5, label='Classical')
plt.plot(alpha_smooth, quantum_smooth, linewidth=2.5, label='Quantum')

plt.scatter(traffic_counts, travel_times[0], s=50)
plt.scatter(traffic_counts, travel_times[1], s=50)
plt.scatter(traffic_counts, travel_times[2], s=50)
plt.scatter(traffic_counts, travel_times[3], s=50)

plt.xlabel('Vehicle Count')
plt.ylabel('Average Travel Time (s)')
plt.title('Travel Time vs Vehicle Count')

plt.ylim(50, 150)

plt.gca().invert_yaxis()

plt.legend()
plt.grid()

plt.show()

# Waiting Time

fixed_smooth = make_interp_spline(traffic_counts, waiting_times[0])(alpha_smooth)
queue_smooth = make_interp_spline(traffic_counts, waiting_times[1])(alpha_smooth)
classical_smooth = make_interp_spline(traffic_counts, waiting_times[2])(alpha_smooth)
quantum_smooth = make_interp_spline(traffic_counts, waiting_times[3])(alpha_smooth)

plt.figure()

plt.plot(alpha_smooth, fixed_smooth, linewidth=2.5, label='Fixed')
plt.plot(alpha_smooth, queue_smooth, linewidth=2.5, label='Queue')
plt.plot(alpha_smooth, classical_smooth, linewidth=2.5, label='Classical')
plt.plot(alpha_smooth, quantum_smooth, linewidth=2.5, label='Quantum')

plt.scatter(traffic_counts, waiting_times[0], s=50)
plt.scatter(traffic_counts, waiting_times[1], s=50)
plt.scatter(traffic_counts, waiting_times[2], s=50)
plt.scatter(traffic_counts, waiting_times[3], s=50)

plt.xlabel('Vehicle Count')
plt.ylabel('Average Waiting Time (s)')
plt.title('Waiting Time vs Vehicle Count')

plt.ylim(15, 70)

plt.gca().invert_yaxis()

plt.legend()
plt.grid()

plt.show()

# Throughput

fixed_smooth = make_interp_spline(traffic_counts, throughputs[0])(alpha_smooth)
queue_smooth = make_interp_spline(traffic_counts, throughputs[1])(alpha_smooth)
classical_smooth = make_interp_spline(traffic_counts, throughputs[2])(alpha_smooth)
quantum_smooth = make_interp_spline(traffic_counts, throughputs[3])(alpha_smooth)

plt.figure()

plt.plot(alpha_smooth, fixed_smooth, linewidth=2.5, label='Fixed')
plt.plot(alpha_smooth, queue_smooth, linewidth=2.5, label='Queue')
plt.plot(alpha_smooth, classical_smooth, linewidth=2.5, label='Classical')
plt.plot(alpha_smooth, quantum_smooth, linewidth=2.5, label='Quantum')

plt.scatter(traffic_counts, throughputs[0], s=50)
plt.scatter(traffic_counts, throughputs[1], s=50)
plt.scatter(traffic_counts, throughputs[2], s=50)
plt.scatter(traffic_counts, throughputs[3], s=50)

plt.xlabel('Vehicle Count')
plt.ylabel('Average Throughput (vehicles/s)')
plt.title('Throughput vs Vehicle Count')

plt.ylim(15, 70)

plt.gca().invert_yaxis()

plt.legend()
plt.grid()