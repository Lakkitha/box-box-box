"""
Exploration script: reverse-engineer the exact lap time formula.

Key insight: this is a synthetic problem with likely "nice" round coefficients.
We use precomputed stint data for fast simulation and search systematically.

Formula:
  lap_time = base_lap_time + compound_offset[tire]
           + max(0, tire_age - cliff[tire]) * deg_rate[tire] * (temp_base + temp_coeff * track_temp)
"""

import json
import os
import time

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

TIRE_IDX = {"SOFT": 0, "MEDIUM": 1, "HARD": 2}


def load_races(path):
    with open(path, "r") as f:
        return json.load(f)


def load_first_n_files(n=1):
    hist_dir = os.path.join(DATA_DIR, "historical_races")
    files = sorted(os.listdir(hist_dir))
    races = []
    for fn in files[:n]:
        races.extend(load_races(os.path.join(hist_dir, fn)))
    return races


def precompute_race(race):
    """Extract parameter-independent features for fast simulation."""
    cfg = race["race_config"]
    total_laps = cfg["total_laps"]

    drivers = []
    for strat in race["strategies"].values():
        tire = strat["starting_tire"]
        pit_map = {ps["lap"]: ps["to_tire"] for ps in strat["pit_stops"]}
        num_pits = len(strat["pit_stops"])

        stints = []
        stint_tire = TIRE_IDX[tire]
        stint_len = 0
        for lap in range(1, total_laps + 1):
            stint_len += 1
            if lap in pit_map:
                stints.append((stint_tire, stint_len))
                stint_tire = TIRE_IDX[pit_map[lap]]
                stint_len = 0
        stints.append((stint_tire, stint_len))

        drivers.append((strat["driver_id"], stints, num_pits))

    expected = race.get("finishing_positions", None)
    return {
        "base": cfg["base_lap_time"],
        "pit": cfg["pit_lane_time"],
        "temp": cfg["track_temp"],
        "laps": total_laps,
        "drivers": drivers,
        "expected": expected,
    }


def predict(pc, co, deg, cliff, tb, tc):
    """Predict finishing order for a precomputed race."""
    temp_f = tb + tc * pc["temp"]
    times = []
    for did, stints, num_pits in pc["drivers"]:
        t = pc["base"] * pc["laps"] + pc["pit"] * num_pits
        for tire_i, slen in stints:
            t += co[tire_i] * slen
            c = cliff[tire_i]
            if slen > c:
                k = slen - c
                t += k * (k + 1) / 2.0 * deg[tire_i] * temp_f
        times.append((did, t))
    times.sort(key=lambda x: x[1])
    return [d for d, _ in times]


def accuracy(pcs, co, deg, cliff, tb, tc):
    ok = 0
    for pc in pcs:
        if predict(pc, co, deg, cliff, tb, tc) == pc["expected"]:
            ok += 1
    return ok / len(pcs)


def main():
    t0 = time.time()
    print("Loading races...")
    full = load_first_n_files(1)
    print(f"Loaded {len(full)} races.")

    pcs = [precompute_race(r) for r in full]
    sample = pcs[:50]
    print(f"Pre-computed. Using {len(sample)} for fast sweeps.\n")

    # ─── PHASE 1: offsets only ───────────────────────────────────────────
    print("=== PHASE 1: Compound offsets (no degradation) ===")
    best1 = 0
    best_co = [0, 0, 0]
    no_deg = [0, 0, 0]
    no_cliff = [999, 999, 999]

    for si in range(-20, 1):
        s = si * 0.1
        for hi in range(0, 25):
            h = hi * 0.1
            co = [s, 0.0, h]
            a = accuracy(sample, co, no_deg, no_cliff, 1.0, 0.0)
            if a > best1:
                best1 = a
                best_co = co[:]
                print(f"  S={s:+.1f} H={h:+.1f} => {a:.4f}")

    print(f"Phase 1: {best1:.4f}  co={best_co}")

    # ─── PHASE 2: degradation (temp_factor=1, cliff=0) ──────────────────
    print("\n=== PHASE 2: Degradation (cliff=0, temp=1) ===")
    best2 = 0
    best_deg = [0, 0, 0]

    # Since the formula is: deg * temp_factor * sum_of_age_over_cliff
    # With temp_factor=1, we sweep deg directly. But temp_factor varies per race!
    # The issue: if temp_factor=1 is wrong, deg found here will be wrong too.
    #
    # Let's try a different approach: maybe temp doesn't interact with degradation.
    # Maybe the formula is simpler:
    #   lap_time = base + offset + age * deg_rate[tire]
    # (no cliff, no temp interaction with degradation at all)

    # Or maybe: deg_rate already includes temp (i.e., temp only affects degradation
    # as a multiplier):
    #   lap_time = base + offset + max(0, age - cliff) * deg[tire] * f(temp)

    # Let's first figure out: does temperature affect the result at ALL?
    # Group races by temperature and check if zero-deg accuracy varies.
    from collections import defaultdict
    temp_groups = defaultdict(list)
    for pc in pcs:
        temp_groups[pc["temp"]].append(pc)

    print("\n  Zero-deg accuracy by temperature:")
    for temp in sorted(temp_groups.keys()):
        group = temp_groups[temp]
        if len(group) >= 5:
            a = accuracy(group, best_co, no_deg, no_cliff, 1.0, 0.0)
            print(f"    temp={temp}: {a:.4f} ({len(group)} races)")

    # Try simple linear degradation: lap_time = base + offset + (age-1) * rate
    # (cliff=1, meaning first lap has no degradation)
    print("\n  Trying deg with cliff=0, step 0.01:")
    for dsi in range(0, 30):
        ds = dsi * 0.01
        for dmi in range(0, 20):
            dm = dmi * 0.01
            for dhi in range(0, 15):
                dh = dhi * 0.01
                deg = [ds, dm, dh]
                a = accuracy(sample, best_co, deg, [0, 0, 0], 1.0, 0.0)
                if a > best2:
                    best2 = a
                    best_deg = deg[:]
                    print(f"  S={ds:.2f} M={dm:.2f} H={dh:.2f} => {a:.4f}")

    print(f"Phase 2: {best2:.4f}  deg={best_deg}")

    # ─── PHASE 2b: cliff sweep ──────────────────────────────────────────
    print("\n=== PHASE 2b: Cliffs ===")
    best2b = best2
    best_cliff = [0, 0, 0]
    for cs in range(0, 12):
        for cm in range(0, 12):
            for ch in range(0, 15):
                a = accuracy(sample, best_co, best_deg, [cs, cm, ch], 1.0, 0.0)
                if a > best2b:
                    best2b = a
                    best_cliff = [cs, cm, ch]
                    print(f"  cs={cs} cm={cm} ch={ch} => {a:.4f}")

    print(f"Phase 2b: {best2b:.4f}  cliff={best_cliff}")

    # ─── PHASE 3: Temperature ───────────────────────────────────────────
    print("\n=== PHASE 3: Temperature ===")
    best3 = best2b
    best_tb, best_tc = 1.0, 0.0

    for tbi in range(-50, 200):
        tb = tbi * 0.01
        for tci in range(-50, 100):
            tc = tci * 0.001
            a = accuracy(sample, best_co, best_deg, best_cliff, tb, tc)
            if a > best3:
                best3 = a
                best_tb, best_tc = tb, tc
                print(f"  tb={tb:.2f} tc={tc:.3f} => {a:.4f}")

    print(f"Phase 3: {best3:.4f}  tb={best_tb} tc={best_tc}")

    # ─── PHASE 4: Fine-tune on full 1000 ────────────────────────────────
    print("\n=== PHASE 4: Validate + fine-tune on full 1000 ===")
    full_acc = accuracy(pcs, best_co, best_deg, best_cliff, best_tb, best_tc)
    print(f"Initial full accuracy: {full_acc:.4f}")

    # Refine offsets
    for _ in range(3):
        improved = False

        # Offsets at 0.01
        sc, hc = best_co[0], best_co[2]
        for dsi in range(-15, 16):
            for dhi in range(-15, 16):
                co = [round(sc + dsi * 0.01, 4), 0.0, round(hc + dhi * 0.01, 4)]
                a = accuracy(pcs, co, best_deg, best_cliff, best_tb, best_tc)
                if a > full_acc:
                    full_acc = a
                    best_co = co[:]
                    improved = True
                    print(f"  (off) S={co[0]:.4f} H={co[2]:.4f} => {a:.4f}")

        # deg at 0.002
        dc = best_deg[:]
        for dsi in range(-10, 11):
            for dmi in range(-10, 11):
                for dhi in range(-10, 11):
                    deg = [max(0, round(dc[0] + dsi * 0.002, 5)),
                           max(0, round(dc[1] + dmi * 0.002, 5)),
                           max(0, round(dc[2] + dhi * 0.002, 5))]
                    a = accuracy(pcs, best_co, deg, best_cliff, best_tb, best_tc)
                    if a > full_acc:
                        full_acc = a
                        best_deg = deg[:]
                        improved = True
                        print(f"  (deg) S={deg[0]:.5f} M={deg[1]:.5f} H={deg[2]:.5f} => {a:.4f}")

        # temp at 0.005/0.0005
        for dtbi in range(-10, 11):
            tb = round(best_tb + dtbi * 0.005, 5)
            for dtci in range(-10, 11):
                tc = round(best_tc + dtci * 0.0005, 6)
                a = accuracy(pcs, best_co, best_deg, best_cliff, tb, tc)
                if a > full_acc:
                    full_acc = a
                    best_tb, best_tc = tb, tc
                    improved = True
                    print(f"  (temp) tb={tb:.5f} tc={tc:.6f} => {a:.4f}")

        # cliffs
        cc = best_cliff[:]
        for cs in range(max(0, cc[0]-2), cc[0]+3):
            for cm in range(max(0, cc[1]-2), cc[1]+3):
                for ch in range(max(0, cc[2]-2), cc[2]+3):
                    a = accuracy(pcs, best_co, best_deg, [cs, cm, ch], best_tb, best_tc)
                    if a > full_acc:
                        full_acc = a
                        best_cliff = [cs, cm, ch]
                        improved = True
                        print(f"  (cliff) S={cs} M={cm} H={ch} => {a:.4f}")

        if not improved:
            break

    # ─── RESULTS ─────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("FINAL RESULTS")
    print("=" * 60)
    print(f"Accuracy (1000 races): {full_acc:.4f}")
    print(f"compound_offset: SOFT={best_co[0]}, MEDIUM=0.0, HARD={best_co[2]}")
    print(f"deg_rate:        SOFT={best_deg[0]}, MEDIUM={best_deg[1]}, HARD={best_deg[2]}")
    print(f"cliff:           SOFT={best_cliff[0]}, MEDIUM={best_cliff[1]}, HARD={best_cliff[2]}")
    print(f"temp_base:       {best_tb}")
    print(f"temp_coeff:      {best_tc}")
    print(f"\nFormula:")
    print(f"  lap_time = base + co[tire] + max(0, age - cliff[tire]) * deg[tire] * (tb + tc * temp)")

    # ─── Cross-validation ────────────────────────────────────────────────
    print("\n--- Cross-validation ---")
    hist_dir = os.path.join(DATA_DIR, "historical_races")
    files = sorted(os.listdir(hist_dir))
    if len(files) > 1:
        r2 = load_races(os.path.join(hist_dir, files[1]))
        pc2 = [precompute_race(r) for r in r2]
        a2 = accuracy(pc2, best_co, best_deg, best_cliff, best_tb, best_tc)
        print(f"Batch 2: {a2:.4f}")

    # Test cases
    print("\n--- Test cases ---")
    test_in = os.path.join(DATA_DIR, "test_cases", "inputs")
    test_out = os.path.join(DATA_DIR, "test_cases", "expected_outputs")
    if os.path.exists(test_in):
        ok = total = 0
        for fn in sorted(os.listdir(test_in)):
            if not fn.endswith(".json"):
                continue
            with open(os.path.join(test_in, fn)) as f:
                tc_data = json.load(f)
            exp_path = os.path.join(test_out, fn)
            if not os.path.exists(exp_path):
                continue
            with open(exp_path) as f:
                exp = json.load(f)
            pc = precompute_race(tc_data)
            pred = predict(pc, best_co, best_deg, best_cliff, best_tb, best_tc)
            total += 1
            if pred == exp["finishing_positions"]:
                ok += 1
        print(f"Test accuracy: {ok}/{total}")

    print(f"\nTotal time: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
