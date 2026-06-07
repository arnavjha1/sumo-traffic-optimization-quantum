# Route Generation and Demand Estimation Methodology

This study required a reproducible procedure for estimating both traffic demand and vehicle route choice within the 2x2 SUMO network. Rather than assigning vehicle volumes and route probabilities manually, the simulation inputs were derived from observed Seattle traffic datasets and converted into hourly inflow rates, intersection-level movement probabilities, route probabilities, and finally SUMO-compatible route flows.

The methodology estimates two central quantities. The first is hourly inflow, denoted \(I_h\), measured in vehicles per hour. This value determines the number of vehicles entering the simulated network during hour \(h\). The second is \(\alpha\), a unitless intersection-level continuation probability. In this project, \(\alpha\) represents the estimated probability that a vehicle continues along the dominant corridor at an intersection rather than departing from that corridor. This value is applied repeatedly at each routing decision within the grid, not only once when a vehicle enters the network.

The overall pipeline can be summarized as follows: Seattle hourly count data is used to estimate 24 hourly traffic constants and an average hourly inflow value; Seattle directional flow-count data is combined with the traffic signal inventory to estimate \(\alpha\); the hourly constants and \(\alpha\) are used to construct route probabilities through the 2x2 grid; and the route probabilities are multiplied by hourly inflow values to produce a SUMO `.rou.xml` file. The implementation is reproducible through the project files `data_analysis/calc_traffic_over_time.py`, `data_analysis/calc_alpha.py`, `data_analysis/route_probability_gen.py`, and `data_analysis/route_gen_2x2.py`. Figure 1 summarizes the full data-to-simulation pipeline.

```text
Seattle Hourly Counts
        |
        v
Hourly Constants and Average Inflow

Seattle Flow Counts + Signal Inventory
        |
        v
Signal Assignment and Candidate Filtering
        |
        v
Alpha Estimation

Hourly Constants + Average Inflow + Alpha
        |
        v
Route Probabilities
        |
        v
SUMO Route File
        |
        v
Simulation
```

## Dataset Sources and Preprocessing

Two Seattle traffic datasets provide the empirical basis for the route-generation procedure. The first, Traffic Count Studies by Hour Bins, is used to estimate hourly traffic demand. It contains daily traffic count observations organized into hourly bins. The relevant fields include a total daily volume, `TOTAL`, hourly totals `HR01_TOTAL` through `HR24_TOTAL`, and contextual fields such as `WEEKDAY` and `HOLIDAY_YN`. These columns make it possible to estimate how a typical day of traffic is distributed across 24 hours.

The second dataset, Traffic Study Flow Counts, is used to estimate directional corridor continuation. The relevant fields include directional flow information, `STUDY_DIRFLOW`, volume measures such as `STUDY_AWDT` and `STUDY_ADT`, street identifiers, and projected coordinates. `STUDY_AWDT` is preferred as the traffic volume estimate because it represents average weekday daily traffic; `STUDY_ADT` is used as a fallback when weekday daily traffic is unavailable. The coordinate fields allow each directional count station to be spatially associated with a nearby signalized intersection.

The alpha estimation also uses the Seattle signal/intersection inventory. The relevant fields include signal identifiers and descriptions, geographic coordinates, and projected coordinates. These records provide the candidate signalized intersections to which directional count stations can be assigned.

The local project data contains 445,410 hourly count rows, 62,220 flow-count records, and 15,497 signal/intersection records. After filtering the hourly count data for high-volume, weekday, non-holiday observations, 102,306 valid rows remain. These dataset sizes support a large-sample estimate of demand and routing behavior, although the estimates remain approximations rather than exact measurements of the simulated grid.

## Hourly Inflow Estimation

Hourly inflow was estimated from the Traffic Count Studies by Hour Bins dataset. The purpose of this stage was to convert observed daily traffic profiles into a normalized 24-hour demand distribution. Before calculation, numeric values were cleaned so that comma-formatted counts could be treated as integers.

Only rows satisfying the following conditions were retained:

1. `TOTAL >= 10000`
2. `WEEKDAY` is not Saturday or Sunday
3. `HOLIDAY_YN = N`

This filtering removes low-volume observations, weekend demand patterns, and holiday traffic patterns. The filtered set is therefore intended to approximate ordinary weekday urban traffic rather than all possible traffic conditions.

For each valid observation \(i\) and hour \(h\), the hourly traffic constant was calculated as the fraction of the daily total occurring during that hour:

\[
\iota_{i,h} = \frac{HR_{i,h}}{TOTAL_i}
\]

The final hourly constant for hour \(h\) was then computed by averaging this ratio over all \(N\) valid observations:

\[
\bar{\iota}_h = \frac{1}{N}\sum_{i=1}^{N}\frac{HR_{i,h}}{TOTAL_i}
\]

The average hourly traffic value was calculated from the total filtered traffic volume:

\[
I_{\text{avg}} = \frac{\sum_{i=1}^{N} TOTAL_i}{24N}
\]

The resulting file, `data_analysis/generated_data/calculated_hourly_constants.csv`, contains 24 hourly constants and a repeated average hourly traffic value. In the current generated output, \(I_{\text{avg}}\) is approximately 975.70 vehicles per hour. This value is the average hourly demand estimate derived from the filtered hour-bin dataset; it is distinct from the larger signal-level directional flow totals used later for alpha estimation. The hourly constants sum to 1.0, so they define a normalized daily traffic profile. The largest constants occur during the afternoon peak period, with the highest value at hour 18.

For route generation, the hourly inflow value is reconstructed as:

\[
I_h = I_{\text{avg}} \cdot \iota_h \cdot 24
\]

The factor of 24 converts the average hourly value back into a day-scaled hourly demand curve. This produces a separate vehicles-per-hour value for each simulated hour.

## Alpha Estimation from Directional Flow Counts

The parameter \(\alpha\) was estimated from directional flow-count records near signalized intersections. Conceptually, \(\alpha\) is treated as an intersection-level continuation probability: it estimates the probability that a vehicle proceeds along the dominant corridor through an intersection instead of departing from that corridor. This interpretation is appropriate for route generation because vehicles in the 2x2 grid may encounter multiple intersections, and a routing decision is required at each one.

Unlike a route-selection probability, \(\alpha\) is not assigned once at network entry. It is applied at every intersection encountered by a vehicle. Consequently, complete route probabilities emerge from repeated applications of \(\alpha\) across a sequence of intersection decisions rather than from a single route choice at the start of a trip. This distinction is central to the methodology: \(\alpha\) models local movement behavior, while the route probability model converts repeated local decisions into complete network routes.

The Traffic Study Flow Counts dataset does not provide direct vehicle trajectories or observed left, right, and through movements. Therefore, \(\alpha\) was estimated from directional corridor continuation rather than measured turn counts. Directional count stations were first cleaned by retaining records with valid coordinates, positive traffic volume, and a supported direction bucket: N, S, E, W, NE, NW, SE, or SW. The preferred volume field was `STUDY_AWDT`, with `STUDY_ADT` used as a fallback.

Each count station was then assigned to the nearest signalized intersection using projected coordinate distance. A nearest-neighbor search was performed against the signal inventory, and a count station was retained only if its nearest signal was within 150 feet. This threshold was selected because it is approximately the spacing at which a count station can reasonably be attributed to a single signalized intersection while avoiding assignment ambiguity in dense downtown corridors. The cutoff reduces the risk of assigning a count station to an unrelated nearby intersection and limits overcounting where multiple signalized intersections are close together.

After assignment, directional volumes were aggregated at the signal level. For each signal, the total assigned flow \(u\) was computed along with total volume in each direction bucket. This produced signal-level directional flow summaries, including northbound, southbound, eastbound, westbound, and diagonal directional volumes. After assigning directional count stations to nearby signals, 1,754 signal-level directional flow summaries were produced.

Candidate intersections were then filtered to improve the reliability of the alpha estimate. A signal was retained only if it had between 4 and 8 assigned count stations, a maximum station distance no greater than 150 feet, at least 3 nonzero directional buckets, and total volume between the 10th and 90th percentiles of signal-level volume. Signal descriptions associated with unusual roadway features, such as ramps, bridges, trails, dead ends, or similar special cases, were excluded. These criteria focus the estimate on filtered candidate intersections that resemble ordinary urban signalized intersections with sufficient directional coverage. The objective was not to maximize the number of retained intersections, but to maximize confidence that each retained intersection had enough directional evidence and represented a conventional signalized intersection. This explains why the pipeline reduces the 1,754 signal-level summaries to 59 filtered candidate signals.

For each candidate signal, four opposing corridor pairs were evaluated:

```text
NS   = N + S
EW   = E + W
NESW = NE + SW
NWSE = NW + SE
```

The dominant corridor, \(C_{dom}\), was defined as the corridor pair with the largest total directional volume. The continuation ratio was calculated as:

\[
\text{continuation ratio} = \frac{C_{\text{dom}}}{u}
\]

The departure ratio was defined as the remaining non-dominant share:

\[
\text{departure ratio} = 1 - \frac{C_{\text{dom}}}{u}
\]

The movement probabilities used in the route model were then defined as:

\[
\alpha_{\text{straight}} = \frac{C_{\text{dom}}}{u}
\]

\[
\alpha_{\text{left}} = \alpha_{\text{right}} =
\frac{1 - \alpha_{\text{straight}}}{2}
\]

The left/right split is a modeling approximation. It does not imply that actual left-turn and right-turn volumes are equal at Seattle intersections. Instead, because the available data does not contain turn trajectories, the non-continuation probability is divided symmetrically so that the route generator can distinguish left and right departures while preserving the empirically estimated total departure probability.

The current citywide alpha summary is based on 59 filtered candidate signals. The resulting mean movement probabilities are:

\[
\alpha_{\text{straight}} = 0.7063
\]

\[
\alpha_{\text{left}} = 0.1469
\]

\[
\alpha_{\text{right}} = 0.1469
\]

The median straight continuation probability is approximately 0.7139. The closeness of the mean and median straight values suggests that the estimate is not dominated by a small number of extreme intersections and that dominant-corridor continuation is reasonably stable across the filtered candidate set.

The estimated continuation probability is also consistent with expected urban arterial behavior. In corridor-oriented street networks, a majority of vehicles typically continue along the dominant through corridor, while a smaller fraction departs onto cross streets or connecting approaches. A value near 0.7 therefore provides a plausible basis for route generation: it represents dominant continuation as the most likely movement without eliminating the substantial share of vehicles that turn or otherwise depart from the primary corridor.

## Route Probability Construction

Route probabilities were constructed for the 2x2 SUMO grid using the alpha-derived movement probabilities. The grid contains four internal intersections, labeled A1, B1, A0, and B0, with internal edges connecting adjacent intersections and outside edges representing network entries and exits. Routes begin from one of eight outside starting edges:

```text
-E6, -E7, -E0, -E1, -E5, -E3, -E4, -E2
```

From each starting edge, all valid routes were generated up to three intersection decisions. At each intersection, the outgoing movement was classified as straight, left, right, or U-turn based on the vehicle's incoming direction. U-turns were excluded. Straight, left, and right movements were assigned probabilities \(\alpha_{\text{straight}}\), \(\alpha_{\text{left}}\), and \(\alpha_{\text{right}}\), respectively.

A route is represented as an ordered edge sequence. For example:

```text
-E7 A1B1 B1B0 E2
```

This route enters from outside edge `-E7`, travels from A1 to B1, then from B1 to B0, and exits through E2. Because alpha is applied at every intersection decision, the probability of a complete route is the product of the movement probabilities along the route:

\[
P(\text{route}) = \prod_{j=1}^{k} P(m_j)
\]

where \(m_j\) is the movement made at decision \(j\). For example, a route with movement sequence straight, right, straight has probability:

\[
P(\text{route}) =
\alpha_{\text{straight}} \cdot
\alpha_{\text{right}} \cdot
\alpha_{\text{straight}}
\]

After raw route probabilities were computed, probabilities were normalized independently for each starting edge \(s\):

\[
P_{\text{norm}}(r \mid s) =
\frac{P_{\text{raw}}(r)}
{\sum_{r' \in s} P_{\text{raw}}(r')}
\]

This normalization ensures that the complete set of generated routes from each outside entry edge sums to 1.0 before route probabilities are converted into SUMO flow rates.

## Route Probability Coverage

The route generator uses a maximum of three intersection decisions. Routes requiring more than three decisions are excluded because they represent a small share of the modeled probability mass while increasing route-set size and simulation complexity. This rule preserves the dominant route choices through the 2x2 grid while avoiding an unnecessarily large number of low-probability circulating paths.

The current generated route-probability file contains 72 total routes. Since the network has 8 outside starting edges, this corresponds to 9 generated routes per starting edge. For each starting edge, the raw probability mass retained by the three-decision route set is approximately 0.9816, while approximately 0.0184 is discarded. Thus, the generated routes preserve about 98.16% of the modeled probability mass and exclude about 1.84% associated with longer routes.

This level of coverage indicates that the overwhelming majority of likely vehicle behavior is preserved while substantially reducing route-generation complexity. The excluded routes are not impossible, but their combined modeled probability is small enough that including them would add complexity with limited effect on the aggregate route distribution.

Consequently, the route-generation model captures nearly all expected vehicle behavior while keeping the route set computationally manageable for repeated SUMO simulation runs.

## SUMO Route File Generation

The final SUMO route file is generated by combining hourly demand estimates with normalized route probabilities. The route-generation stage uses three generated data products: `calculated_hourly_constants.csv`, `alpha_citywide_summary.csv`, and `generated_route_probabilities.csv`.

For each hour \(h\), the hourly inflow \(I_h\) is calculated from the average hourly traffic and the corresponding hourly constant. For each route \(r\) that begins from starting edge \(s\), the route-specific SUMO flow is then calculated as:

\[
\text{vehsPerHour}_{h,r} =
I_h \cdot P_{\text{norm}}(r \mid s)
\]

The output file, `routes_2x2/routes2x2_data.rou.xml`, contains a vehicle type definition, route definitions, and hourly flow definitions. In the current generated output, the file contains 72 route definitions and 1,728 hourly route flows, corresponding to 72 routes across 24 simulated hours.

This procedure produces deterministic SUMO route flows while preserving a direct connection to the empirical estimates. Each hourly vehicle flow can be traced back to an hourly demand constant, an average inflow estimate, and a normalized route probability. As a result, the simulation input is reproducible and can be regenerated if the underlying datasets or modeling assumptions are updated.

## Reliability and Assumptions

The methodology is empirically grounded because both traffic demand and routing probabilities are estimated from observed Seattle traffic data. The hourly inflow profile is derived from a large set of filtered hourly count observations, and \(\alpha\) is derived from directional flow patterns at filtered candidate intersections. These filters improve reliability by removing observations that are likely to be less representative of ordinary weekday urban traffic, including holidays, weekends, low-volume records, distant count-station assignments, extreme-volume intersections, and special roadway features.

However, filtering does not eliminate all uncertainty. The Seattle datasets provide a data-derived basis for simulation inputs, but the 2x2 SUMO network is an abstracted grid rather than a direct reconstruction of a specific Seattle corridor. The resulting parameters should therefore be interpreted as large-sample estimates of realistic urban traffic behavior rather than exact measurements for the simulated network.

The estimated straight-continuation probability is consistent with typical urban arterial behavior, where many vehicles continue along a dominant corridor and a smaller share departs onto cross streets. The similarity between the mean and median \(\alpha_{\text{straight}}\) values further supports the stability of the estimate across the filtered candidate intersections. Nonetheless, \(\alpha\) remains an estimated routing probability based on available directional count data.

## Methodological Limitations

The primary limitation is that the alpha values are estimated from directional corridor continuation patterns rather than direct turn movement counts. The source flow-count data identifies directional volumes near intersections, but it does not provide complete vehicle trajectories or observed left, right, and through movements for individual vehicles. Consequently, \(\alpha_{\text{straight}}\) is interpreted as a data-derived estimate of dominant-corridor continuation, while \(\alpha_{\text{left}}\) and \(\alpha_{\text{right}}\) are approximated by evenly splitting the remaining departure probability. This symmetry is a modeling assumption used for route generation and should not be interpreted as evidence that actual left-turn and right-turn volumes are equal.

A second limitation is that Seattle traffic data is used as a proxy for realistic urban traffic behavior in a simplified 2x2 SUMO grid. This improves empirical grounding compared with arbitrary route assignment, but it does not capture every local geometric, behavioral, or temporal feature of the original Seattle network. The generated routes and flows are therefore best understood as reproducible, data-derived simulation inputs rather than a complete reconstruction of observed Seattle traffic.
