# Supplementary traffic population and delay comparison

WORKING RESULTS: QAOA collection may be incomplete. This report reads only completed, successful evaluation runs; calibration and validation runs are excluded.

All runs use alpha 0.7 and a 600-second cutoff. Entries are the mean ± sample SD across optimizer seeds. These are fixed-demand optimizer replications, not independent traffic-demand replications. No controller decisions are modified.

## 2x2

| Measure | Classical global SA | Classical stochastic | QAOA |
|---|---:|---:|---:|
| Successful / planned runs | 20 / 20 | 20 / 20 | 5 / 20 |
| Completed-trip travel (s) | 97.371 ± 0.000 | 95.733 ± 0.988 | 96.592 ± 1.820 |
| Completed-trip waiting (s) | 47.327 ± 0.000 | 46.095 ± 0.892 | 46.911 ± 1.761 |
| Completed trips | 928.000 ± 0.000 | 945.650 ± 15.836 | 936.200 ± 25.743 |
| Unfinished trips | 178.000 ± 0.000 | 183.800 ± 9.041 | 185.000 ± 5.477 |
| Removed trips | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| Completion fraction of entered vehicles | 0.839 ± 0.000 | 0.837 ± 0.006 | 0.835 ± 0.000 |
| In-network time loss (vehicle-s) | 83515.370 ± 0.000 | 80604.367 ± 1042.027 | 80862.230 ± 266.604 |
| In-network stopped waiting (vehicle-s) | 51877.000 ± 0.000 | 49385.650 ± 456.100 | 49898.200 ± 664.387 |
| Pending insertion at cutoff | 5566.000 ± 0.000 | 5542.550 ± 21.917 | 5550.800 ± 31.220 |
| Insertion backlog integral (vehicle-s) | 1643862.000 ± 0.000 | 1644455.700 ± 4099.160 | 1647485.400 ± 7479.699 |

Failed seeds: Classical global SA: []; Classical stochastic: []; QAOA: []

## 3x3

| Measure | Classical global SA | Classical stochastic | QAOA |
|---|---:|---:|---:|
| Successful / planned runs | 20 / 20 | 20 / 20 | 0 / 20 |
| Completed-trip travel (s) | 197.520 ± 0.826 | 198.273 ± 6.561 | Pending |
| Completed-trip waiting (s) | 112.880 ± 0.722 | 112.257 ± 5.313 | Pending |
| Completed trips | 944.700 ± 4.669 | 960.150 ± 48.387 | Pending |
| Unfinished trips | 362.300 ± 10.378 | 344.200 ± 18.168 | Pending |
| Removed trips | 0.000 ± 0.000 | 0.000 ± 0.000 | Pending |
| Completion fraction of entered vehicles | 0.723 ± 0.005 | 0.736 ± 0.019 | Pending |
| In-network time loss (vehicle-s) | 208535.667 ± 1443.437 | 207740.319 ± 6660.235 | Pending |
| In-network stopped waiting (vehicle-s) | 145787.850 ± 503.116 | 144291.950 ± 7345.216 | Pending |
| Pending insertion at cutoff | 8921.000 ± 14.216 | 8923.650 ± 37.142 | Pending |
| Insertion backlog integral (vehicle-s) | 2679942.950 ± 1883.241 | 2677132.900 ± 7234.802 | Pending |

Failed seeds: Classical global SA: []; Classical stochastic: []; QAOA: []

## Definitions and interpretation

- Completed-trip averages describe only vehicles arriving before the cutoff. Unfinished-trip eventual travel times are not imputed.
- In-network time loss is SUMO timeLoss accumulated by all entered vehicles, including completed, unfinished, and removed vehicles. It differs from stopped waiting.
- In-network stopped waiting sums SUMO waitingTime over the same entered population.
- Pending vehicles have not entered the network. Their backlog is reported separately; the backlog integral is a discrete right-endpoint sum and must not be described as SUMO timeLoss.
- Completion fraction uses entered vehicles as its denominator; it excludes vehicles pending insertion and future demand.
- Assess trip averages together with completions, unfinished trips, total delay, and backlog. Lower completed-trip means alone do not establish a system-level improvement.
- The current instrumented global baseline is labeled simulated annealing according to its implementation. Exhaustive energy diagnostics do not make action selection exact.
- Final effect estimates and claims await the complete QAOA batch. A zero SD describes the observed seeds only; it does not imply certainty under other demand scenarios.
