# Common-Hamiltonian calibration findings

Replayed six successful 600-decision QAOA recordings (three seeds per grid,
alpha 0.7) through the existing classical stochastic controller. Tested budgets
8, 16, 32, 64, 128 with seeds 101–103; additional budgets 2, 4, 6 are retained
in `../stochastic_replay_low_budget_results`. All 48 comparisons completed.

Each grid supplies 1,800 recorded Hamiltonians. Each classical setting is
evaluated on exactly these Hamiltonians. These are calibration data, not
independent traffic evaluations. Exact reference minima and QAOA selected
energies were independently checked during replay.

## Findings

- 2x2: QAOA recovered the exact minimum on 99.61% of decisions. Budget 32
  recovered it on 99.22–99.50% across the three classical seeds. This is a
  candidate for recovery-rate matching, not a matched gap distribution: the
  classical mean gap was about 0.02 versus QAOA's about 0.04.
- 3x3: QAOA recovery was 38.78%, with mean gap 25.84. Even budgets 2–8 had
  roughly 50–51% recovery and mean gaps about 9.6–9.9. Larger budgets improved
  classical energy quality further. None of the tested settings matches QAOA.
- The first annealing restart starts from the previous signal state. Shrinking
  the budget therefore does not make this controller equivalent to random
  sampling. Do not claim a distribution match or deliberately degrade it based
  on downstream traffic results.

## Next decision

Do not freeze a supposedly matched 3x3 controller from this sweep. Options are
to evaluate it explicitly as an unmatched approximate stochastic control (the
reviewer describes matching as preferable), or extend the optimizer family
with a documented random-initialization option and recalibrate using energy
quality only. Independent evaluation seeds and traffic accounting remain
necessary. No main-study results were replaced and no final evaluation was run.
