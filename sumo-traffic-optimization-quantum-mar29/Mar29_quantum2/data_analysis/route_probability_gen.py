from pathlib import Path
import pandas as pd

ALPHA_CSV = Path("data_analysis/generated_data/alpha_citywide_summary.csv")
OUTPUT_CSV = Path("data_analysis/generated_data/generated_route_probabilities.csv")

MAX_DECISIONS = 3

# Nodes: A1 top-left, B1 top-right, A0 bottom-left, B0 bottom-right
# Each option: outgoing_edge, next_node, movement_direction
GRAPH = {
    "A1": [
        ("E7", None, "W"),        # exit west
        ("A1B1", "B1", "E"),      # go east
        ("A1A0", "A0", "S"),      # go south
        ("E6", None, "N"),        # exit north
    ],
    "B1": [
        ("B1A1", "A1", "W"),
        ("E1", None, "E"),
        ("B1B0", "B0", "S"),
        ("E0", None, "N"),
    ],
    "A0": [
        ("E5", None, "W"),
        ("A0B0", "B0", "E"),
        ("E3", None, "S"),
        ("A0A1", "A1", "N"),
    ],
    "B0": [
        ("B0A0", "A0", "W"),
        ("E4", None, "E"),
        ("E2", None, "S"),
        ("B0B1", "B1", "N"),
    ],
}

# Starting edges: edge enters node while moving in direction
STARTS = {
    "-E7": ("A1", "S"),
    "-E6": ("A1", "E"),
    "-E0": ("B1", "S"),
    "-E1": ("B1", "W"),
    "-E5": ("A0", "E"),
    "-E3": ("A0", "N"),
    "-E4": ("B0", "W"),
    "-E2": ("B0", "N"),
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