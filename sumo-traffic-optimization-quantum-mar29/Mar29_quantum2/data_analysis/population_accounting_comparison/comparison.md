# Supplementary traffic population and delay comparison

COMPLETE EVALUATION: 20 successful runs per controller and grid. Calibration and validation runs are excluded. Confidence intervals for controller differences are provided in effect_estimates.md.

All runs use alpha 0.7 and a 600-second cutoff. Entries are the mean Â± sample SD across optimizer seeds. These are fixed-demand optimizer replications, not independent traffic-demand replications. No controller decisions are modified.

## 2x2

| Measure | Classical global SA | Classical stochastic | QAOA |
|---|---:|---:|---:|
| Successful / planned runs | 20 / 20 | 20 / 20 | 20 / 20 |
| Completed-trip travel (s) | 97.371 Â± 0.000 | 95.733 Â± 0.988 | 96.023 Â± 1.453 |
| Completed-trip waiting (s) | 47.327 Â± 0.000 | 46.095 Â± 0.892 | 46.410 Â± 1.406 |
| Completed trips | 928.000 Â± 0.000 | 945.650 Â± 15.836 | 942.900 Â± 19.785 |
| Unfinished trips | 178.000 Â± 0.000 | 183.800 Â± 9.041 | 185.650 Â± 5.733 |
| Removed trips | 0.000 Â± 0.000 | 0.000 Â± 0.000 | 0.000 Â± 0.000 |
| Completion fraction of entered vehicles | 0.839 Â± 0.000 | 0.837 Â± 0.006 | 0.836 Â± 0.002 |
| In-network time loss (vehicle-s) | 83515.370 Â± 0.000 | 80604.367 Â± 1042.027 | 80771.571 Â± 593.872 |
| In-network stopped waiting (vehicle-s) | 51877.000 Â± 0.000 | 49385.650 Â± 456.100 | 49643.850 Â± 543.855 |
| Pending insertion at cutoff | 5566.000 Â± 0.000 | 5542.550 Â± 21.917 | 5543.450 Â± 24.937 |
| Insertion backlog integral (vehicle-s) | 1643862.000 Â± 0.000 | 1644455.700 Â± 4099.160 | 1645684.300 Â± 6020.449 |

Failed seeds: Classical global SA: []; Classical stochastic: []; QAOA: []

## 3x3

| Measure | Classical global SA | Classical stochastic | QAOA |
|---|---:|---:|---:|
| Successful / planned runs | 20 / 20 | 20 / 20 | 20 / 20 |
| Completed-trip travel (s) | 197.520 Â± 0.826 | 198.273 Â± 6.561 | 198.158 Â± 6.220 |
| Completed-trip waiting (s) | 112.880 Â± 0.722 | 112.257 Â± 5.313 | 111.540 Â± 4.956 |
| Completed trips | 944.700 Â± 4.669 | 960.150 Â± 48.387 | 972.300 Â± 38.075 |
| Unfinished trips | 362.300 Â± 10.378 | 344.200 Â± 18.168 | 345.050 Â± 18.092 |
| Removed trips | 0.000 Â± 0.000 | 0.000 Â± 0.000 | 0.000 Â± 0.000 |
| Completion fraction of entered vehicles | 0.723 Â± 0.005 | 0.736 Â± 0.019 | 0.738 Â± 0.017 |
| In-network time loss (vehicle-s) | 208535.667 Â± 1443.437 | 207740.319 Â± 6660.235 | 205183.662 Â± 5884.700 |
| In-network stopped waiting (vehicle-s) | 145787.850 Â± 503.116 | 144291.950 Â± 7345.216 | 141069.650 Â± 6799.077 |
| Pending insertion at cutoff | 8921.000 Â± 14.216 | 8923.650 Â± 37.142 | 8910.650 Â± 25.205 |
| Insertion backlog integral (vehicle-s) | 2679942.950 Â± 1883.241 | 2677132.900 Â± 7234.802 | 2675118.050 Â± 5186.981 |

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
