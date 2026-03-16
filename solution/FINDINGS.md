# Exploration Findings

## Formula Structure (Confirmed)

```
lap_time = base_lap_time
         + compound_offset[tire]
         + max(0, tire_age - cliff[tire]) * deg_rate[tire] * (temp_base + temp_coeff * track_temp)
```

- `tire_age`: starts at 0, incremented to 1 before the first lap calculation each stint.
- **Pit stop** at end of a lap: adds `pit_lane_time` to total, resets `tire_age` to 0, changes compound.
- Total race time = sum of all lap times + pit penalties.
- Finishing order = sorted by total race time (ascending).

## Tiebreaker Rule (Confirmed)

When two drivers have **identical total race time** (same compound sequence, same pit timing), the tiebreaker is **driver ID in ascending order** (D008 beats D011 beats D015, etc.). Verified across multiple races with groups of identically-strategied drivers.

## Cliff Values (Partially Confirmed)

The "cliff" is the number of laps a tire performs with zero degradation. After that, degradation kicks in linearly per lap.

| Compound | Cliff (laps) | Confidence | Evidence                                                                                                                                                                                    |
| -------- | ------------ | ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| HARD     | ~20          | High       | For N=25, ALL H→M and H→S drivers pit at exactly lap 20, regardless of temperature. This is consistent with cliff_H=20: the driver uses the full zero-degradation window then switches.     |
| SOFT     | ~8–9         | Medium     | S→M and S→H optimal pit at N=25 is 7–9. Since SOFT is the fastest compound (negative offset), drivers maximize time on it → pit at cliff_S.                                                 |
| MEDIUM   | ~15–18       | Medium     | M→H optimal pit at N=25 is 16–18. Since MEDIUM is faster than HARD, drivers maximize time on it → pit at cliff_M. But the variability suggests temperature interaction affects the optimum. |

## Compound Offsets (Approximate)

MEDIUM = 0.0 (reference). SOFT is negative (faster), HARD is positive (slower).

- **SOFT offset**: roughly −0.5 to −1.0 (exact value not yet pinned down)
- **HARD offset**: roughly +0.5 to +1.0

The zero-degradation-only search found SOFT≈−1.0, HARD≈+0.8 at ~18% accuracy, but these are unreliable without degradation in the model.

## Temperature Effect (Key Unsolved Piece)

Temperature **strongly** affects results. Critical evidence:

- With offsets only (no degradation), accuracy grouped by temperature:
  - **temps 28–33**: ~7–13% accuracy
  - **temps < 27 or > 34**: **0% accuracy**
- This means degradation (scaled by temperature) is essential for ALL races outside the 28–33 band. The temp_factor multiplier on degradation is the mechanism.
- Higher temperature → faster degradation (optimal M→H pit moves earlier: pit=19 at temp=29 vs pit=18 at temp=30).
- Temperature range in data: **18–42°C**.

## Degradation Rates (Not Yet Determined)

Grid search with cliff=0 and temp_factor=1.0 failed to improve beyond the offset-only baseline. This confirms:

1. Cliffs are non-zero and critical to the model.
2. Temperature interaction (`temp_base + temp_coeff * track_temp`) is required — degradation without the temperature multiplier doesn't work.
3. The rates, cliffs, and temperature coefficients must all be found **jointly**, not sequentially.

## Data Characteristics

| Property             | Range                                                  |
| -------------------- | ------------------------------------------------------ |
| Tracks               | Bahrain, COTA, Monaco, Monza, Silverstone, Spa, Suzuka |
| Track temperature    | 18–42°C                                                |
| Total laps           | 25–55 (approx)                                         |
| Base lap time        | 80.0–95.0 s (step 0.1)                                 |
| Pit lane time        | 20.0–24.0 s (step 0.1)                                 |
| Drivers per race     | 20 (D001–D020, always all 20)                          |
| Pit stops per driver | 1 or 2 (91.9% are 1-stop)                              |
| Historical races     | 30,000 across ~30 files                                |
| Test cases           | 100                                                    |

## What Still Needs Solving

1. **Exact cliff values** — HARD≈20 is near-certain; SOFT and MEDIUM need confirmation.
2. **Exact degradation rates** — `deg_rate[SOFT]`, `deg_rate[MEDIUM]`, `deg_rate[HARD]`.
3. **Exact temperature coefficients** — `temp_base` and `temp_coeff`.
4. **Exact compound offsets** — need to be co-determined with degradation.
5. **Joint optimization** — all 10 parameters (3 offsets, 3 deg rates, 3 cliffs, 1 temp formula with 2 params) must be found together. Sequential search failed because parameters interact.

## Recommended Next Steps / Way forward

1. **Fix HARD cliff at 20** and reduce the search space.
2. **Use the pairwise constraint approach** on same-strategy driver groups: for drivers with the same compound sequence but different pit timing, the ranking directly constrains the parameters via analytic expressions.
3. **Try scipy with cliff fixed** — reduce to 7 continuous parameters (2 offsets, 3 deg rates, 2 temp coefficients) with cliff_H=20, cliff_S∈{7,8,9}, cliff_M∈{15,16,17,18}.
4. **Validate on test cases** (100 available with expected outputs) once accuracy on training data exceeds 95%.
