import string
import random

# --------------------------------------------------
# CONFIG
# --------------------------------------------------

numcols = 5
numrows = 5

top_edges = ["top0","top1","top2","top3","top4"]
bottom_edges = ["bottom0","bottom1","bottom2","bottom3","bottom4"]

left_edges = ["left4","left3","left2","left1","left0"]
right_edges = ["right4","right3","right2","right1","right0"]

NUM_SAMPLES = 1000
TRAFFIC = 400000 / NUM_SAMPLES

ALPHA = 0.7
BETA = (1-ALPHA)/2
GAMMA = (1-ALPHA)/2

TOTAL_EDGES = (numrows + numcols) * 2
MAX_MOVES = 50

column_ids = list(string.ascii_uppercase)

route_id = 0
flow_id = 0

routes = []
flows = []

# --------------------------------------------------
# HELPERS
# --------------------------------------------------

def node(x,y):
    return f"{column_ids[x]}{y}"

def edge(a,b):
    return f"{a}{b}"

def direction(px,py,x,y):
    if px is None:
        return None
    if x>px: return "R"
    if x<px: return "L"
    if y>py: return "U"
    if y<py: return "D"

# --------------------------------------------------
# LANE SELECTION LOGIC (KEY PART)
# --------------------------------------------------
def get_lane_from_first_turn(edges):

    if len(edges) < 2:
        return None

    first = edges[0]
    second = edges[1]

    # -----------------------------
    # ENTRY DIRECTION (from edge name)
    # -----------------------------
    if first.startswith("top"):
        entry_dir = "D"
    elif first.startswith("bottom"):
        entry_dir = "U"
    elif first.startswith("left"):
        entry_dir = "R"
    elif first.startswith("right"):
        entry_dir = "L"
    else:
        return None

    # -----------------------------
    # EXTRACT GRID NODES
    # -----------------------------
    # first edge: "... -> A0"
    # find first capital letter = start of grid node
    idx = next(i for i, c in enumerate(first) if c.isupper())
    mid = first[idx:]   # e.g. "A0"

    # second edge: "A0B0"
    mid2 = second[:len(second)//2]
    nxt  = second[len(second)//2:]

    if mid != mid2:
        return None

    # -----------------------------
    # PARSE GRID NODES ONLY
    # -----------------------------
    def parse(n):
        if n[0] not in column_ids:
            return None
        return column_ids.index(n[0]), int(n[1:])

    m = parse(mid)
    n = parse(nxt)

    if m is None or n is None:
        return None

    mx, my = m
    nx, ny = n

    move_dir = direction(mx, my, nx, ny)

    # -----------------------------
    # LANE LOGIC
    # -----------------------------
    if move_dir == entry_dir:
        return "1"  # straight

    turn_map = {
        ("U","L"): "0",
        ("U","R"): "2",
        ("D","R"): "0",
        ("D","L"): "2",
        ("L","D"): "0",
        ("L","U"): "2",
        ("R","U"): "0",
        ("R","D"): "2",
    }

    return turn_map.get((entry_dir, move_dir), "1")

# --------------------------------------------------
# STORE ROUTE
# --------------------------------------------------

def store_route(edges,turns,moves):

    global route_id, flow_id

    cars = round(
        (TRAFFIC / TOTAL_EDGES)
        * (ALPHA ** (moves-turns))
        * (BETA ** turns)
    )

    if cars <= 0:
        return

    edge_string = " ".join(edges)

    routes.append(
        f'    <route id="r{route_id}" edges="{edge_string}"/>'
    )

   #lane = get_lane_from_first_turn(edges)

   #if lane not in ["0", "1", "2"]:
   #    lane = "best"
    
    lane = "1"

    flows.append(
        f'    <flow id="flow{flow_id}" type="car" route="r{route_id}" begin="0" end="600" vehsPerHour="{cars}" departLane="{lane}" departSpeed="max" departPos="base"/>'
    )

    route_id += 1
    flow_id += 1

# --------------------------------------------------
# RANDOM WALK GENERATOR
# --------------------------------------------------

def random_route(start_edge, start_x, start_y, initial_dir):

    x, y = start_x, start_y
    px, py = None, None
    prev_dir = initial_dir

    path = [start_edge]
    moves = 0
    turns = 0

    while moves < MAX_MOVES:

        neighbors = [
            (x+1,y),
            (x-1,y),
            (x,y+1),
            (x,y-1)
        ]

        valid = []

        for nx, ny in neighbors:

            if nx == px and ny == py:
                continue

            step_dir = direction(x,y,nx,ny)

            if prev_dir is None or step_dir == prev_dir:
                prob = ALPHA
            elif step_dir in ["L","R"] and prev_dir in ["U","D"]:
                prob = BETA
            elif step_dir in ["U","D"] and prev_dir in ["L","R"]:
                prob = GAMMA
            else:
                prob = BETA

            valid.append((nx, ny, step_dir, prob))

        if not valid:
            return

        total = sum(v[3] for v in valid)
        r = random.random() * total

        cum = 0
        for nx, ny, step_dir, prob in valid:
            cum += prob
            if r <= cum:
                break

        # exit conditions
        if nx < 0:
            idx = numrows-1-ny
            exit_node = left_edges[idx]
            path.append(edge(node(x,y), exit_node))
            break

        elif nx >= numcols:
            idx = numrows-1-ny
            exit_node = right_edges[idx]
            path.append(edge(node(x,y), exit_node))
            break

        elif ny < 0:
            exit_node = bottom_edges[nx]
            path.append(edge(node(x,y), exit_node))
            break

        elif ny >= numrows:
            exit_node = top_edges[nx]
            path.append(edge(node(x,y), exit_node))
            break

        path.append(edge(node(x,y), node(nx,ny)))

        if prev_dir is not None and step_dir != prev_dir:
            turns += 1

        px, py = x, y
        x, y = nx, ny
        prev_dir = step_dir
        moves += 1

    store_route(path, turns, moves)

# --------------------------------------------------
# GENERATE TRAFFIC
# --------------------------------------------------

def generate():

    for _ in range(NUM_SAMPLES):

        side = random.choice(["top","bottom","left","right"])

        if side == "top":
            x = random.randint(0, numcols-1)
            random_route(edge(top_edges[x], node(x, numrows-1)), x, numrows-1, "D")

        elif side == "bottom":
            x = random.randint(0, numcols-1)
            random_route(edge(bottom_edges[x], node(x, 0)), x, 0, "U")

        elif side == "left":
            y = random.randint(0, numrows-1)
            idx = numrows-1-y
            random_route(edge(left_edges[idx], node(0,y)), 0, y, "R")

        else:
            y = random.randint(0, numrows-1)
            idx = numrows-1-y
            random_route(edge(right_edges[idx], node(numcols-1,y)), numcols-1, y, "L")

generate()

# --------------------------------------------------
# WRITE FILE
# --------------------------------------------------

with open("routes.rou.xml","w") as f:

    f.write("<routes>\n\n")
    
    f.write("""    <vType id="car"
       accel="2.6"
       decel="4.5"
       maxSpeed="13.9"
       length="5"/>\n\n""")

    f.write("    <!-- ROUTES -->\n\n")

    for r in routes:
        f.write(r+"\n")

    f.write("\n    <!-- FLOWS -->\n\n")

    for fl in flows:
        f.write(fl+"\n")

    f.write("\n</routes>\n")