import string

# --------------------------------------------------
# CONFIG
# --------------------------------------------------

numcols = 2
numrows = 2

# top/bottom go left -> right
top_edges = ["E6", "E0"]
bottom_edges = ["E3", "E2"]

# left/right go top -> bottom
left_edges = ["E7", "E5"]
right_edges = ["E1", "E4"]

TRAFFIC = 5000
ALPHA = 0.7

column_ids = list(string.ascii_uppercase)

MAX_MOVES = numcols + numrows + 2

route_id = 0
possible_routes = []
flows = []


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
# ROUTE STORAGE
# --------------------------------------------------

def store_route(edges, turns, moves):
    global route_id

    prob = round(TRAFFIC * (ALPHA ** (moves - turns)) * ((1.0 - ALPHA) ** turns))

    edge_string = " ".join(edges)

    routes.append(f'    <route id="r{route_id}" edges="{edge_string}"/>')

    flows.append(
        f'    <flow id="flow{route_id}" type="car" route="r{route_id}" begin="0" end="300" vehsPerHour="{prob}"/>'
    )

    route_id += 1


# --------------------------------------------------
# RECURSIVE PATH GENERATOR
# --------------------------------------------------

def recursive_route(x, y, px, py, prev_dir, moves, turns, path):

    if moves > MAX_MOVES:
        return

    if px is not None:
        path = path + [edge(node(px, py), node(x, y))]

    neighbors = [
        (x+1, y),
        (x-1, y),
        (x, y+1),
        (x, y-1)
    ]

    for nx, ny in neighbors:

        if nx == px and ny == py:
            continue

        step_dir = direction(x, y, nx, ny)

        new_turns = turns
        if prev_dir is not None and step_dir != prev_dir:
            new_turns += 1

        new_moves = moves + 1

        # exits

        if nx < 0:
            idx = numrows - 1 - ny
            exit_edge = left_edges[idx]
            possible_routes.append((path + [exit_edge], new_moves, new_turns))

        elif nx >= numcols:
            idx = numrows - 1 - ny
            exit_edge = right_edges[idx]
            possible_routes.append((path + [exit_edge], new_moves, new_turns))

        elif ny < 0:
            exit_edge = bottom_edges[nx]
            possible_routes.append((path + [exit_edge], new_moves, new_turns))

        elif ny >= numrows:
            exit_edge = top_edges[nx]
            possible_routes.append((path + [exit_edge], new_moves, new_turns))

        else:
            recursive_route(nx, ny, x, y, step_dir, new_moves, new_turns, path)


# --------------------------------------------------
# GENERATE ROUTES FROM ALL ENTRY POINTS
# --------------------------------------------------

# entering from TOP
for x in range(numcols):
    start_edge = "-" + top_edges[x]
    recursive_route(x, numrows-1, None, None, "D", 0, 0, [start_edge])

# entering from BOTTOM
for x in range(numcols):
    start_edge = "-" + bottom_edges[x]
    recursive_route(x, 0, None, None, "U", 0, 0, [start_edge])

# entering from LEFT
for y in range(numrows):
    start_edge = "-" + left_edges[numrows-1-y]
    recursive_route(0, y, None, None, "R", 0, 0, [start_edge])

# entering from RIGHT
for y in range(numrows):
    start_edge = "-" + right_edges[numrows-1-y]
    recursive_route(numcols-1, y, None, None, "L", 0, 0, [start_edge])


# --------------------------------------------------
# BUILD ROUTES
# --------------------------------------------------

routes = []

for edges, moves, turns in possible_routes:
    store_route(edges, turns, moves)


# --------------------------------------------------
# WRITE XML FILE
# --------------------------------------------------

with open("routes.rou.xml", "w") as f:

    f.write("<routes>\n")

    f.write("""
    <!-- Vehicle type -->
    <vType id="car"
           accel="2.6"
           decel="4.5"
           maxSpeed="13.9"
           length="5"/>
""")

    f.write("""
    <!-- Route probabilities -->
    <parameters>
        <prob id="ALPHA" value="0.6"/>
        <prob id="BETA"  value="0.25"/>
        <prob id="GAMMA" value="0.15"/>
    </parameters>
""")

    f.write("\n    <!-- ROUTES -->\n\n")

    for r in routes:
        f.write(r + "\n")

    f.write("\n    <!-- FLOWS -->\n\n")

    for fl in flows:
        f.write(fl + "\n")

    f.write("</routes>\n")