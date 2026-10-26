# Run-level controller differences

Each estimate is the first controller minus the comparator. Negative values favor the first controller for travel, waiting, delay, unfinished trips, removals and backlog; positive values favor it for completions and completion fraction. Unfinished counts still need to be interpreted with entry and completion populations.

Intervals are independent two-sample percentile bootstrap 95% confidence intervals using 50,000 resamples of whole runs (fixed random seed 20261025). Numeric seed labels are not treated as paired traffic scenarios. Demand is fixed; uncertainty concerns optimizer randomness only. These are pointwise exploratory intervals, without adjustment for multiple comparisons. An interval spanning zero does not establish equivalence. No per-decision or per-vehicle pseudoreplication is used.

## 2x2: QAOA minus Classical global SA

| Metric | Mean difference | 95% CI | Relative to comparator |
|---|---:|---:|---:|
| completed_mean_travel_seconds | -1.3481 | [-1.9417, -0.6835] | -1.38% |
| completed_mean_waiting_seconds | -0.9168 | [-1.5406, -0.2738] | -1.94% |
| completed_trips | +14.9000 | [+6.1000, +22.6500] | +1.61% |
| unfinished_trips | +7.6500 | [+5.0000, +10.0000] | +4.30% |
| removed_trips | +0.0000 | [+0.0000, +0.0000] | Undefined (zero comparator) |
| completion_fraction_of_departed | -0.0035 | [-0.0042, -0.0024] | -0.42% |
| network_time_loss_seconds | -2743.7985 | [-3030.3865, -2531.4525] | -3.29% |
| network_waiting_seconds | -2233.1500 | [-2452.0500, -1989.0500] | -4.30% |
| pending_insertion_at_cutoff | -22.5500 | [-32.3500, -11.3500] | -0.41% |
| pending_insertion_vehicle_seconds_sampled | +1822.3000 | [-473.7500, +4553.1500] | +0.11% |
| all_insertion_delay_seconds | +1822.3000 | [-473.7500, +4553.1500] | +0.11% |
| time_loss_plus_insertion_delay_seconds | -921.4985 | [-3030.7695, +1662.0970] | -0.05% |
| realized_demand_trips | +0.0000 | [+0.0000, +0.0000] | +0.00% |

## 2x2: Classical stochastic minus Classical global SA

| Metric | Mean difference | 95% CI | Relative to comparator |
|---|---:|---:|---:|
| completed_mean_travel_seconds | -1.6375 | [-2.0393, -1.2036] | -1.68% |
| completed_mean_waiting_seconds | -1.2314 | [-1.5962, -0.8334] | -2.60% |
| completed_trips | +17.6500 | [+10.5000, +23.9000] | +1.90% |
| unfinished_trips | +5.8000 | [+1.5500, +9.3500] | +3.26% |
| removed_trips | +0.0000 | [+0.0000, +0.0000] | Undefined (zero comparator) |
| completion_fraction_of_departed | -0.0017 | [-0.0040, +0.0011] | -0.21% |
| network_time_loss_seconds | -2911.0030 | [-3378.7890, -2496.0560] | -3.49% |
| network_waiting_seconds | -2491.3500 | [-2681.5000, -2289.4000] | -4.80% |
| pending_insertion_at_cutoff | -23.4500 | [-32.4500, -13.7500] | -0.42% |
| pending_insertion_vehicle_seconds_sampled | +593.7000 | [-1081.1500, +2465.5500] | +0.04% |
| all_insertion_delay_seconds | +593.7000 | [-1081.1500, +2465.5500] | +0.04% |
| time_loss_plus_insertion_delay_seconds | -2317.3030 | [-3692.2040, -794.7330] | -0.13% |
| realized_demand_trips | +0.0000 | [+0.0000, +0.0000] | +0.00% |

## 2x2: QAOA minus Classical stochastic

| Metric | Mean difference | 95% CI | Relative to comparator |
|---|---:|---:|---:|
| completed_mean_travel_seconds | +0.2894 | [-0.4356, +1.0641] | +0.30% |
| completed_mean_waiting_seconds | +0.3146 | [-0.3746, +1.0539] | +0.68% |
| completed_trips | -2.7500 | [-13.6500, +7.9000] | -0.29% |
| unfinished_trips | +1.8500 | [-2.5500, +6.6500] | +1.01% |
| removed_trips | +0.0000 | [+0.0000, +0.0000] | Undefined (zero comparator) |
| completion_fraction_of_departed | -0.0018 | [-0.0047, +0.0007] | -0.22% |
| network_time_loss_seconds | +167.2045 | [-335.2390, +689.4585] | +0.21% |
| network_waiting_seconds | +258.2000 | [-40.5550, +568.4500] | +0.52% |
| pending_insertion_at_cutoff | +0.9000 | [-13.1500, +15.0013] | +0.02% |
| pending_insertion_vehicle_seconds_sampled | +1228.6000 | [-1814.9050, +4381.4537] | +0.07% |
| all_insertion_delay_seconds | +1228.6000 | [-1816.3950, +4401.2500] | +0.07% |
| time_loss_plus_insertion_delay_seconds | +1395.8045 | [-1348.2112, +4322.5390] | +0.08% |
| realized_demand_trips | +0.0000 | [+0.0000, +0.0000] | +0.00% |

## 3x3: QAOA minus Classical global SA

| Metric | Mean difference | 95% CI | Relative to comparator |
|---|---:|---:|---:|
| completed_mean_travel_seconds | +0.6381 | [-2.0748, +3.2962] | +0.32% |
| completed_mean_waiting_seconds | -1.3398 | [-3.4250, +0.8438] | -1.19% |
| completed_trips | +27.6000 | [+10.7000, +43.3000] | +2.92% |
| unfinished_trips | -17.2500 | [-25.9500, -8.2000] | -4.76% |
| removed_trips | +0.0000 | [+0.0000, +0.0000] | Undefined (zero comparator) |
| completion_fraction_of_departed | +0.0150 | [+0.0071, +0.0224] | +2.07% |
| network_time_loss_seconds | -3352.0055 | [-5929.1574, -764.8116] | -1.61% |
| network_waiting_seconds | -4718.2000 | [-7539.7587, -1703.1938] | -3.24% |
| pending_insertion_at_cutoff | -10.3500 | [-22.3513, +2.2000] | -0.12% |
| pending_insertion_vehicle_seconds_sampled | -4824.9000 | [-7159.8575, -2463.2350] | -0.18% |
| all_insertion_delay_seconds | -4824.9000 | [-7155.3550, -2426.3875] | -0.18% |
| time_loss_plus_insertion_delay_seconds | -8176.9055 | [-11738.9511, -4487.6694] | -0.28% |
| realized_demand_trips | +0.0000 | [+0.0000, +0.0000] | +0.00% |

## 3x3: Classical stochastic minus Classical global SA

| Metric | Mean difference | 95% CI | Relative to comparator |
|---|---:|---:|---:|
| completed_mean_travel_seconds | +0.7536 | [-2.0436, +3.5936] | +0.38% |
| completed_mean_waiting_seconds | -0.6225 | [-2.9062, +1.6638] | -0.55% |
| completed_trips | +15.4500 | [-5.8013, +35.5000] | +1.64% |
| unfinished_trips | -18.1000 | [-26.5000, -8.6500] | -5.00% |
| removed_trips | +0.0000 | [+0.0000, +0.0000] | Undefined (zero comparator) |
| completion_fraction_of_departed | +0.0129 | [+0.0037, +0.0207] | +1.78% |
| network_time_loss_seconds | -795.3480 | [-3641.4745, +2155.2178] | -0.38% |
| network_waiting_seconds | -1495.9000 | [-4495.7050, +1783.9575] | -1.03% |
| pending_insertion_at_cutoff | +2.6500 | [-14.5000, +19.3000] | +0.03% |
| pending_insertion_vehicle_seconds_sampled | -2810.0500 | [-6050.9575, +317.4562] | -0.10% |
| all_insertion_delay_seconds | -2810.0500 | [-6003.9012, +355.3200] | -0.10% |
| time_loss_plus_insertion_delay_seconds | -3605.3980 | [-8714.2921, +1620.3043] | -0.12% |
| realized_demand_trips | +0.0000 | [+0.0000, +0.0000] | +0.00% |

## 3x3: QAOA minus Classical stochastic

| Metric | Mean difference | 95% CI | Relative to comparator |
|---|---:|---:|---:|
| completed_mean_travel_seconds | -0.1155 | [-4.0224, +3.7314] | -0.06% |
| completed_mean_waiting_seconds | -0.7174 | [-3.7600, +2.3862] | -0.64% |
| completed_trips | +12.1500 | [-13.9000, +38.7013] | +1.27% |
| unfinished_trips | +0.8500 | [-10.3000, +11.6000] | +0.25% |
| removed_trips | +0.0000 | [+0.0000, +0.0000] | Undefined (zero comparator) |
| completion_fraction_of_departed | +0.0021 | [-0.0086, +0.0132] | +0.29% |
| network_time_loss_seconds | -2556.6575 | [-6423.7681, +1199.4824] | -1.23% |
| network_waiting_seconds | -3222.3000 | [-7563.5650, +1063.3000] | -2.23% |
| pending_insertion_at_cutoff | -13.0000 | [-32.1000, +6.3500] | -0.15% |
| pending_insertion_vehicle_seconds_sampled | -2014.8500 | [-5754.7025, +1849.2063] | -0.08% |
| all_insertion_delay_seconds | -2014.8500 | [-5792.3000, +1825.9500] | -0.08% |
| time_loss_plus_insertion_delay_seconds | -4571.5075 | [-10949.8743, +1727.1846] | -0.16% |
| realized_demand_trips | +0.0000 | [+0.0000, +0.0000] | +0.00% |

## Reporting limits

All-zero removed-trip counts produce a degenerate interval for the observed runs, not evidence that removals are impossible. The zero-variance 2x2 global baseline is likewise conditional on this fixed demand and these optimizer settings. Report insertion backlog separately from SUMO timeLoss. Do not add overlapping waiting and timeLoss measures into a combined delay score.

These supplementary comparisons use the current instrumented global simulated-annealing baseline. They do not by themselves establish conclusions about a different exact action-selecting controller or historical metrics. The stochastic control was calibration-informed but did not pass all energy-distribution matching checks; it is not a validated distribution match.

Welch two-sample tests and Holm-adjusted p values are provided in the JSON and revised statistical tables. Holm adjustment spans all nonconstant metrics, grids, and controller pairs in this exploratory analysis. No primary outcome is claimed to have been prespecified. Welch tests are approximate with 20 potentially skewed optimizer outcomes; interpret alongside distributions and bootstrap estimates. Bootstrap intervals remain pointwise, not simultaneous.