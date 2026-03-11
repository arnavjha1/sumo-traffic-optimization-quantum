import string

# --------------------------------------------------
# CONFIG
# --------------------------------------------------

numcols = 5
numrows = 5

# top/bottom go left -> right
top_edges = ["E6", "E0"]
bottom_edges = ["E3", "E2"]

# left/right go top -> bottom
left_edges = ["E7", "E5"]
right_edges = ["E1", "E4"]

TRAFFIC = 40000  # traffic load
ALPHA = 0.8

TOTAL_EDGES = (numrows + numcols) * 2

column_ids = list(string.ascii_uppercase)
MAX_MOVES = numcols + numrows + 2

route_id = 0
flow_id = 0
possible_routes = []
flows = []
routes = []

# --------------------------------------------------
# HELPERS
# --------------------------------------------------

def node(x, y):
    return f"{column_ids[x]}{y}"

def edge(a, b):
    return f"{a}{b}"

def direction(px, py, x, y):
    if px is None:
        return None
    if x > px: return "R"
    if x < px: return "L"
    if y > py: return "U"
    if y < py: return "D"

# --------------------------------------------------
# STORE ROUTES
# --------------------------------------------------

def store_route(edges, turns, moves):
    global route_id
    global flow_id
    expected_cars = round((TRAFFIC / TOTAL_EDGES) * (ALPHA ** (moves - turns)) * (((1.0 - ALPHA) / 2) ** turns))
    edge_string = " ".join(edges)
    routes.append(f'    <route id="r{route_id}" edges="{edge_string}"/>')
    if expected_cars != 0:
        flows.append(f'    <flow id="flow{flow_id}" type="car" route="r{route_id}" begin="0" end="600" vehsPerHour="{expected_cars}"/>')
        flow_id += 1
    route_id += 1

# --------------------------------------------------
# RECURSIVE ROUTE GENERATOR
# --------------------------------------------------

def recursive_route(x, y, px, py, prev_dir, moves, turns, path, forbidden_exit=None):
    if moves > MAX_MOVES:
        return

    if px is not None:
        path = path + [edge(node(px, py), node(x, y))]

    neighbors = [(x+1, y), (x-1, y), (x, y+1), (x, y-1)]

    for nx, ny in neighbors:
        # prevent U-turns
        if nx == px and ny == py:
            continue

        step_dir = direction(x, y, nx, ny)
        new_turns = turns
        if prev_dir is not None and step_dir != prev_dir:
            new_turns += 1
        new_moves = moves + 1

        # outside edges
        if nx < 0:
            idx = numrows - 1 - ny
            exit_edge = left_edges[idx]
            if exit_edge != forbidden_exit:
                possible_routes.append((path + [exit_edge], new_moves, new_turns))

        elif nx >= numcols:
            idx = numrows - 1 - ny
            exit_edge = right_edges[idx]
            if exit_edge != forbidden_exit:
                possible_routes.append((path + [exit_edge], new_moves, new_turns))

        elif ny < 0:
            exit_edge = bottom_edges[nx]
            if exit_edge != forbidden_exit:
                possible_routes.append((path + [exit_edge], new_moves, new_turns))

        elif ny >= numrows:
            exit_edge = top_edges[nx]
            if exit_edge != forbidden_exit:
                possible_routes.append((path + [exit_edge], new_moves, new_turns))

        else:
            recursive_route(nx, ny, x, y, step_dir, new_moves, new_turns, path, forbidden_exit)

# --------------------------------------------------
# GENERATE ROUTES FROM ALL ENTRY POINTS
# --------------------------------------------------

# top edges
for x in range(numcols):
    start_edge = "-" + top_edges[x]
    recursive_route(x, numrows-1, None, None, "D", 0, 0, [start_edge], forbidden_exit=top_edges[x])

# bottom edges
for x in range(numcols):
    start_edge = "-" + bottom_edges[x]
    recursive_route(x, 0, None, None, "U", 0, 0, [start_edge], forbidden_exit=bottom_edges[x])

# left edges
for y in range(numrows):
    idx = numrows - 1 - y
    start_edge = "-" + left_edges[idx]
    recursive_route(0, y, None, None, "R", 0, 0, [start_edge], forbidden_exit=left_edges[idx])

# right edges
for y in range(numrows):
    idx = numrows - 1 - y
    start_edge = "-" + right_edges[idx]
    recursive_route(numcols-1, y, None, None, "L", 0, 0, [start_edge], forbidden_exit=right_edges[idx])

# --------------------------------------------------
# STORE ROUTES
# --------------------------------------------------

for edges, moves, turns in possible_routes:
    store_route(edges, turns, moves)

# --------------------------------------------------
# WRITE XML FILE
# --------------------------------------------------

with open("routes.rou.xml", "w") as f:
    f.write("<routes>\n\n")
    f.write("""    <!-- Vehicle type -->
    <vType id="car"
           accel="2.6"
           decel="4.5"
           maxSpeed="13.9"
           length="5"/>\n\n""")
    f.write("""    <!-- Route probabilities -->
    <parameters>
        <prob id="ALPHA" value="0.6"/>
        <prob id="BETA"  value="0.25"/>
        <prob id="GAMMA" value="0.15"/>
    </parameters>\n\n""")
    f.write("    <!-- ROUTES -->\n\n")
    for r in routes:
        f.write(r + "\n")
    f.write("\n    <!-- FLOWS -->\n\n")
    for fl in flows:
        f.write(fl + "\n")
    f.write("\n</routes>\n")