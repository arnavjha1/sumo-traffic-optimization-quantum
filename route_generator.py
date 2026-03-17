import string

# --------------------------------------------------
# CONFIG
# --------------------------------------------------

numcols = 5
numrows = 5

# top/bottom go left -> right
top_edges = ["top0","top1","top2","top3","top4"]
bottom_edges = ["bottom0","bottom1","bottom2","bottom3","bottom4"]

# left/right go top -> bottom
left_edges = ["left4","left3","left2","left1","left0"]
right_edges = ["right4","right3","right2","right1","right0"]

TRAFFIC = 40000
ALPHA = 0.33
BETA = ((1-ALPHA)/2)
GAMMA = ((1-ALPHA)/2)

TOTAL_EDGES = (numrows + numcols) * 2
MAX_MOVES = 3*(numcols + numrows + 2)

column_ids = list(string.ascii_uppercase)

route_id = 0
flow_id = 0

routes = []
flows = []
possible_routes = []

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

    global route_id
    global flow_id

    cars = round(
        (TRAFFIC / TOTAL_EDGES)
        * (ALPHA ** (moves-turns))
        * (((1-ALPHA)/2) ** turns)
    )

    edge_string = " ".join(edges)

    routes.append(
        f'    <route id="r{route_id}" edges="{edge_string}"/>'
    )

    if cars>0:

        flows.append(
            f'    <flow id="flow{flow_id}" type="car" route="r{route_id}" begin="0" end="600" vehsPerHour="{cars}"/>'
        )

        flow_id+=1

    route_id+=1


# --------------------------------------------------
# RECURSIVE ROUTE SEARCH
# --------------------------------------------------

def recursive_route(x,y,px,py,prev_dir,moves,turns,path,forbidden_exit):

    if moves>MAX_MOVES:
        return

    # add internal edge
    if px is not None:

        path = path + [ edge(node(px,py),node(x,y)) ]

    neighbors = [
        (x+1,y),
        (x-1,y),
        (x,y+1),
        (x,y-1)
    ]

    for nx,ny in neighbors:

        # prevent U turn
        if nx==px and ny==py:
            continue

        step_dir = direction(x,y,nx,ny)

        new_turns = turns
        if prev_dir is not None and step_dir!=prev_dir:
            new_turns+=1

        new_moves = moves+1

        # --------------------------------
        # EXIT GRID
        # --------------------------------

        if nx<0:

            idx = numrows-1-ny
            exit_node = left_edges[idx]

            if exit_node!=forbidden_exit:

                possible_routes.append(
                    (path+[ edge(node(x,y),exit_node) ],new_moves,new_turns)
                )

        elif nx>=numcols:

            idx = numrows-1-ny
            exit_node = right_edges[idx]

            if exit_node!=forbidden_exit:

                possible_routes.append(
                    (path+[ edge(node(x,y),exit_node) ],new_moves,new_turns)
                )

        elif ny<0:

            exit_node = bottom_edges[nx]

            if exit_node!=forbidden_exit:

                possible_routes.append(
                    (path+[ edge(node(x,y),exit_node) ],new_moves,new_turns)
                )

        elif ny>=numrows:

            exit_node = top_edges[nx]

            if exit_node!=forbidden_exit:

                possible_routes.append(
                    (path+[ edge(node(x,y),exit_node) ],new_moves,new_turns)
                )

        else:

            recursive_route(
                nx,ny,
                x,y,
                step_dir,
                new_moves,
                new_turns,
                path,
                forbidden_exit
            )


# --------------------------------------------------
# GENERATE ENTRY ROUTES
# --------------------------------------------------

# TOP

for x in range(numcols):

    start = top_edges[x]
    start_edge = edge(start,node(x,numrows-1))

    recursive_route(
        x,
        numrows-1,
        None,
        None,
        "D",
        0,
        0,
        [start_edge],
        start
    )

# BOTTOM

for x in range(numcols):

    start = bottom_edges[x]
    start_edge = edge(start,node(x,0))

    recursive_route(
        x,
        0,
        None,
        None,
        "U",
        0,
        0,
        [start_edge],
        start
    )

# LEFT

for y in range(numrows):

    idx = numrows-1-y
    start = left_edges[idx]

    start_edge = edge(start,node(0,y))

    recursive_route(
        0,
        y,
        None,
        None,
        "R",
        0,
        0,
        [start_edge],
        start
    )

# RIGHT

for y in range(numrows):

    idx = numrows-1-y
    start = right_edges[idx]

    start_edge = edge(start,node(numcols-1,y))

    recursive_route(
        numcols-1,
        y,
        None,
        None,
        "L",
        0,
        0,
        [start_edge],
        start
    )


# --------------------------------------------------
# STORE ROUTES
# --------------------------------------------------

for edges,moves,turns in possible_routes:
    store_route(edges,turns,moves)


# --------------------------------------------------
# WRITE ROUTE FILE
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