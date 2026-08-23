from pathlib import Path
import pandas as pd

ALPHA_CSV = Path("data_analysis/generated_data/alpha_citywide_summary.csv")
OUTPUT_CSV = Path("data_analysis/generated_data/generated_route_probabilities.csv")

MAX_DECISIONS = 3

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

    def dfs(node, current_direction, edges, movements, probability, decisions):
        if decisions >= MAX_DECISIONS:
            return

        for out_edge, next_node, out_direction in GRAPH[node]:
            turn = classify_turn(current_direction, out_direction)

            # Avoid U-turns
            if turn == "uturn":
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
                    "decisions": decisions + 1,
                    "raw_probability": new_probability,
                })
            else:
                dfs(
                    next_node,
                    out_direction,
                    new_edges,
                    new_movements,
                    new_probability,
                    decisions + 1,
                )

    dfs(
        start_node,
        start_direction,
        [start_edge],
        [],
        1.0,
        0,
    )

    return routes

def main():
    alpha_summary = pd.read_csv(ALPHA_CSV)

    alpha = {
        "straight": float(alpha_summary["mean_alpha_straight"].iloc[0]),
        "left": float(alpha_summary["mean_alpha_left"].iloc[0]),
        "right": float(alpha_summary["mean_alpha_right"].iloc[0]),
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

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_CSV, index=False)

    print(f"Saved route probability CSV to: {OUTPUT_CSV}")
    print()
    print("Probability sum by starting edge:")
    print(df.groupby("start_edge")["normalized_probability"].sum())

main()