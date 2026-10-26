# Demand, population and insertion-delay audit

All 120 evaluation runs passed the following checks: matching effective network/route-file hashes within each grid; identical vehicle IDs, types and speed factors; matching intended departure times within 0.021 s (XML rounding); zero population residual. Realized demand is 6,672 vehicles for 2x2 and 10,228 for 3x3. This is realized demand emitted by SUMO by the cutoff, not a continuous-rate approximation to route-file flows.

Population identity: realized demand = completed + unfinished + removed + pending insertion. Undeparted tripinfo records also equal the TraCI pending count. No vehicles were removed in these runs.

Total pre-entry delay sums departDelay across BOTH entered and undeparted tripinfo records. For entered vehicles it stops at insertion; for undeparted vehicles it stops at the cutoff. Adding this to entered-vehicle timeLoss joins disjoint pre-entry and in-network phases; it does not add stopped waiting to timeLoss. This supplementary composite is explicitly named time loss plus pre-entry delay and is not SUMO timeLoss alone.

The previous sampled backlog integral remains separate. It approximates pre-entry delay using one-second right-endpoint sampling; do not add that integral again to the raw pre-entry delay.

Metric documentation: https://sumo.dlr.de/docs/Simulation/Output/TripInfo.html ; implementation of undeparted departDelay: https://sumo.dlr.de/daily/doxygen/d1/dc9/_m_s_device___tripinfo_8cpp_source.html .

These checks establish common supplied/realized demand for these experiments, not generalization across traffic-demand scenarios. They do not certify historical exact-baseline provenance.