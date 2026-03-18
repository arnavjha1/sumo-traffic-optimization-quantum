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

# number of simulated routes (controls density)
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

    flows.append(
        f'    <flow id="flow{flow_id}" type="car" route="r{route_id}" begin="0" end="600" vehsPerHour="{cars}" departLane="1"/>'
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

            # prevent U-turn
            if nx == px and ny == py:
                continue

            step_dir = direction(x,y,nx,ny)

            # assign probabilities
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

        # normalize probabilities
        total = sum(v[3] for v in valid)
        r = random.random() * total

        cum = 0
        for nx, ny, step_dir, prob in valid:
            cum += prob
            if r <= cum:
                break

        # check exit
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

        # normal move
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
            random_route(
                edge(top_edges[x], node(x, numrows-1)),
                x, numrows-1, "D"
            )

        elif side == "bottom":
            x = random.randint(0, numcols-1)
            random_route(
                edge(bottom_edges[x], node(x, 0)),
                x, 0, "U"
            )

        elif side == "left":
            y = random.randint(0, numrows-1)
            idx = numrows-1-y
            random_route(
                edge(left_edges[idx], node(0,y)),
                0, y, "R"
            )

        else:
            y = random.randint(0, numrows-1)
            idx = numrows-1-y
            random_route(
                edge(right_edges[idx], node(numcols-1,y)),
                numcols-1, y, "L"
            )

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