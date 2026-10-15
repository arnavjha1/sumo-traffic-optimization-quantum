# Supplementary traffic accounting

The two stochastic `a7.py` controllers now request SUMO tripinfo output with
unfinished and undeparted records. Every run writes a uniquely named XML and
JSON file in `supplementary_traffic_results` (override with
`SUPPLEMENTARY_OUTPUT_DIR`). The calibration runner also embeds the summary
under `supplementary` in each result JSON and exports aggregate CSV columns.

- `completed_trips`: reached the destination by the actual cutoff.
- `unfinished_trips`: departed but not completed at cutoff, including SUMO's
  `vaporized="end"` records. Genuine removals are counted separately.
- `network_time_loss_seconds`: sum of SUMO timeLoss for all departed vehicles,
  including completed, unfinished, and removed trips. Time loss measures travel
  below individual ideal speed; scheduled stops are excluded. Units are
  vehicle-seconds. This is not delay experienced before insertion.
- `network_waiting_seconds`: sum of full-trip waitingTime through the cutoff
  for those same populations, not the rolling TraCI waiting-memory window.
- `completed_mean_travel_seconds` and `completed_mean_waiting_seconds`: SUMO
  tripinfo averages for completed vehicles. Existing legacy printed averages
  remain unchanged; use these explicitly named fields for the supplement.
- `pending_insertion_at_cutoff`: TraCI vehicles waiting for insertion.
- `pending_insertion_vehicle_seconds_sampled`: per-step right-endpoint integral
  of pending vehicle count. Report separately from in-network time loss.
- `departed_insertion_delay_seconds`: departure delay of vehicles that entered;
  do not add this to the pending-count integral (they overlap).
- `undeparted_tripinfo_records`: diagnostic count; not a count of all scheduled
  future demand and not a discarded-demand estimate.
- `teleport_start_events`: events, not unique vehicles or removals.

Departure and arrival counts are reconciled against simulation events. The
runner rejects runs with mismatched accounting. The raw XML remains available
for auditing. Never infer discarded demand from unfinished counts.

The actual cutoff is saved. Compare controllers at the same cutoff and demand.
This instrumentation currently covers the stochastic controllers only; QAOA
and the verified exact controller need identical collection for the final
comparison. No metric retroactively appears in runs started before this change.

After an already-running calibration sweep finishes, rerun the updated runner;
its code/input fingerprint prevents reuse of older results as current results.
Keep evaluation seeds separate from calibration seeds.

Definition source: https://sumo.dlr.de/docs/Simulation/Output/TripInfo.html
