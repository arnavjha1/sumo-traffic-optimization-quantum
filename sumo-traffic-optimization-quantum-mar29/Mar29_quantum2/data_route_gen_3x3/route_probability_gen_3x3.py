from pathlib import Path
import pandas as pd

MAX_TURNS = 3

# Nodes: A1 top-left, B1 top-right, A0 bottom-left, B0 bottom-right
# Each option: outgoing_edge, next_node, movement_direction
GRAPH = {
    # --------------------------------------------------
    # LEFT COLUMN
    # --------------------------------------------------

    "A0": [
        ("A0_1", None, "W"),       # exit west
        ("A0B0", "B0", "E"),       # go east
        ("A0_0", None, "S"),       # exit south
        ("A0A1", "A1", "N"),       # go north
    ],

    "A1": [
        ("A1_1", None, "W"),       # exit west
        ("A1B1", "B1", "E"),       # go east
        ("A1A0", "A0", "S"),       # go south
        ("A1A2", "A2", "N"),       # go north
    ],

    "A2": [
        ("A2_1", None, "W"),       # exit west
        ("A2B2", "B2", "E"),       # go east
        ("A2A1", "A1", "S"),       # go south
        ("A2_0", None, "N"),       # exit north
    ],

    # --------------------------------------------------
    # MIDDLE COLUMN
    # --------------------------------------------------

    "B0": [
        ("B0A0", "A0", "W"),       # go west
        ("B0C0", "C0", "E"),       # go east
        ("B0_0", None, "S"),       # exit south
        ("B0B1", "B1", "N"),       # go north
    ],

    "B1": [
        ("B1A1", "A1", "W"),       # go west
        ("B1C1", "C1", "E"),       # go east
        ("B1B0", "B0", "S"),       # go south
        ("B1B2", "B2", "N"),       # go north
    ],

    "B2": [
        ("B2A2", "A2", "W"),       # go west
        ("B2C2", "C2", "E"),       # go east
        ("B2B1", "B1", "S"),       # go south
        ("B2_0", None, "N"),       # exit north
    ],

    # --------------------------------------------------
    # RIGHT COLUMN
    # --------------------------------------------------

    "C0": [
        ("C0B0", "B0", "W"),       # go west
        ("C0_1", None, "E"),       # exit east
        ("C0_0", None, "S"),        # exit south
        ("C0C1", "C1", "N"),       # go north
    ],

    "C1": [
        ("C1B1", "B1", "W"),       # go west
        ("C1_1", None, "E"),       # exit east
        ("C1C0", "C0", "S"),       # go south
        ("C1C2", "C2", "N"),       # go north
    ],

    "C2": [
        ("C2B2", "B2", "W"),       # go west
        ("C2_1", None, "E"),       # exit east
        ("C2C1", "C1", "S"),       # go south
        ("C2_0", None, "N"),       # exit north
    ],
}

# Starting edges: edge enters node while moving in direction
STARTS = {
    # Bottom boundary -> entering north
    "-A0_0": ("A0", "N"),
    "-B0_0": ("B0", "N"),
    "-C0_0": ("C0", "N"),

    # Left boundary -> entering east
    "-A0_1": ("A0", "E"),
    "-A1_1": ("A1", "E"),
    "-A2_1": ("A2", "E"),

    # Top boundary -> entering south
    "-A2_0": ("A2", "S"),
    "-B2_0": ("B2", "S"),
    "-C2_0": ("C2", "S"),

    # Right boundary -> entering west
    "-C0_1": ("C0", "W"),
    "-C1_1": ("C1", "W"),
    "-C2_1": ("C2", "W"),
}

LEFT_OF = {
    "N": "W",
    "W": "S",
    "S": "E",
    "E": "N",
}

RIGHT_OF = {
    "N": "E",
    "E": "S",
    "S": "W",
    "W": "N",
}

OPPOSITE = {
    "N": "S",
    "S": "N",
    "E": "W",
    "W": "E",
}

def classify_turn(in_dir, out_dir):
    if out_dir == in_dir:
        return "straight"
    if out_dir == LEFT_OF[in_dir]:
        return "left"
    if out_dir == RIGHT_OF[in_dir]:
        return "right"
    return "uturn"

def generate_routes_from_start(start_edge, start_node, start_direction, alpha):
    routes = []

    def dfs(node, current_direction, edges, movements, probability, turn_count, visited_nodes):
        for out_edge, next_node, out_direction in GRAPH[node]:

            # Prevent routes from looping back through an intersection for num_edges > 3, only an issue for the 3x3 grid
            if next_node is not None and next_node in visited_nodes:
                continue

            turn = classify_turn(current_direction, out_direction)

            # Avoid U-turns
            if turn == "uturn":
                continue

            new_turn_count = turn_count

            if turn in ("left", "right"):
                new_turn_count += 1

            if new_turn_count > MAX_TURNS:
                continue

            turn_prob = alpha[turn]
            new_edges = edges + [out_edge]
            new_movements = movements + [turn]
            new_probability = probability * turn_prob

            if next_node is None:
                routes.append({
                    "start_edge": start_edge,
                    "route_edges": " ".join(new_edges),
                    "movement_sequence": " ".join(new_movements),
                    "turns": new_turn_count,
                    "intersections": len(new_movements),
                    "raw_probability": new_probability,
                })
            else:
                dfs(
                    next_node,
                    out_direction,
                    new_edges,
                    new_movements,
                    new_probability,
                    new_turn_count,
                    visited_nodes | {next_node},
                )


    dfs(
        start_node,
        start_direction,
        [start_edge],
        [],
        1.0,
        0,
        {start_node},
    )

    return routes

def main(alpha_straight=0.5):
    alpha_index = int(round(alpha_straight * 10))
    output_csv = Path(
        f"data_route_gen_3x3/generated_data/"
        f"generated_route_probabilities_3x3_a{alpha_index}.csv"
    )

    alpha = {
        "straight": alpha_straight,
        "left": (1.0 - alpha_straight) / 2.0,
        "right": (1.0 - alpha_straight) / 2.0,
    }

    all_routes = []

    for start_edge, (start_node, start_direction) in STARTS.items():
        routes = generate_routes_from_start(
            start_edge,
            start_node,
            start_direction,
            alpha,
        )
        all_routes.extend(routes)

    df = pd.DataFrame(all_routes)

    # Normalize probabilities so routes from the same start edge sum to 1
    df["normalized_probability"] = df.groupby("start_edge")["raw_probability"].transform(
        lambda x: x / x.sum()
    )

    df.insert(0, "route_id", [f"r{i}" for i in range(len(df))])

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False)

    print("\n===== 3x3 ROUTE GENERATION CHECK =====")

    print(f"\nTotal routes generated: {len(df)}")

    print("\nRoutes per starting edge:")
    print(df.groupby("start_edge").size())

    print("\nProbability sum by starting edge:")
    print(
        df.groupby("start_edge")["normalized_probability"].sum()
    )


    print("\nTurn-count distribution:")
    print(df["turns"].value_counts().sort_index())

    print("\nIntersection-count distribution:")
    print(df["intersections"].value_counts().sort_index())

    print("\nMaximum turns:")
    print(df["turns"].max())

    print("\nMaximum intersections traversed:")
    print(df["intersections"].max())


    print("\nSample routes:")
    print(
        df[
            [
                "route_id",
                "start_edge",
                "route_edges",
                "movement_sequence",
                "turns",
                "intersections",
                "normalized_probability",
            ]
        ].head(20).to_string(index=False)
    )

    print("\nLongest-route examples:")
    print(
        df.loc[
            df["turns"] == df["turns"].max(),
            [
                "route_id",
                "start_edge",
                "route_edges",
                "movement_sequence",
                "turns",
                "intersections",
            ],
        ].head(10).to_string(index=False)
    )

    def route_has_repeated_nodes(route_edges):
        edges = route_edges.split()

        visited = set()

        for edge in edges:
            # Internal grid edge like A0B0 means A0 -> B0
            if len(edge) == 4 and edge[0] in "ABC" and edge[2] in "ABC":
                from_node = edge[:2]
                to_node = edge[2:]

                visited.add(from_node)

                if to_node in visited:
                    return True

                visited.add(to_node)

        return False


    repeated_route_count = df["route_edges"].apply(
        route_has_repeated_nodes
    ).sum()

    print("\nRoutes containing repeated intersections:")
    print(repeated_route_count)

    print("\nRoute probability range:")
    print(f"Minimum: {df['normalized_probability'].min():.8f}")
    print(f"Maximum: {df['normalized_probability'].max():.8f}")

    print("\nTotal normalized probability across all starts:")
    print(df["normalized_probability"].sum())

    routes_per_start = df.groupby("start_edge").size()

    print("\nRoute-count symmetry check:")
    print(f"Minimum routes per start: {routes_per_start.min()}")
    print(f"Maximum routes per start: {routes_per_start.max()}")

    if routes_per_start.nunique() == 1:
        print("PASS: all starting edges have equal route counts")
    else:
        print("WARNING: route counts differ across starting edges")

    print("\n===== END 3x3 ROUTE GENERATION CHECK =====")

    print(f"\nSaved route probability CSV to: {output_csv}")

    print("\n===== ALPHA SETTINGS =====")
    print(f"Straight: {alpha['straight']:.2f}")
    print(f"Left:     {alpha['left']:.2f}")
    print(f"Right:    {alpha['right']:.2f}")
    print("==========================\n")

main()