top_edges = ["E6", "E5", "E4"]
bottom_edges = ["E0", "E1", "E2"]
left_edges = ["-E7"]
right_edges = ["E3"]

column_ids = ["A", "B", "C"]
numrows = 2

route_id = 0

def print_route(edges):
    global route_id
    edge_string = " ".join(edges)
    print(f'<route id="r{route_id}" edges="{edge_string}"/>')
    route_id += 1


# Top-left corner routes
for col in column_ids:
    for row in range(1, numrows+1):
        mid = f"{col}{row}{col}{row-1}" if row > 1 else f"{col}{row}B{row}"
        for exit_edge in bottom_edges:
            print_route([left_edges[0], mid, exit_edge])


# Top edge routes
for entry in top_edges:
    for col in column_ids:
        for row in range(1, numrows+1):
            mid = f"{col}{row}{col}{row-1}" if row > 1 else f"{col}{row}B{row}"
            for exit_edge in bottom_edges:
                print_route([entry, mid, exit_edge])


# Right edge routes
for entry in right_edges:
    for col in reversed(column_ids):
        for row in range(1, numrows+1):
            mid = f"{col}{row}{col}{row-1}" if row > 1 else f"{col}{row}B{row}"
            for exit_edge in left_edges:
                print_route([entry, mid, exit_edge])


# Bottom edge routes
for entry in bottom_edges:
    for col in column_ids:
        for row in reversed(range(1, numrows+1)):
            mid = f"{col}{row}{col}{row-1}" if row > 1 else f"{col}{row}B{row}"
            for exit_edge in top_edges:
                print_route([entry, mid, exit_edge])