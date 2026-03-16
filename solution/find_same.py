"""Find driver pairs with ZERO degradation to isolate compound offsets.

If all stints are below their cliff, deg=0, and:
  total_time = base*N + offset[c1]*laps_c1 + offset[c2]*laps_c2 + pits*pit

For two drivers with same pit count but different compound mix:
  time_A - time_B = offset_diff * laps_diff

This gives us exact offset differences.
"""
import json, os, sys
from collections import defaultdict
sys.stdout.reconfigure(encoding='utf-8')

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

print("Loading all races...")
all_races = []
for fname in sorted(os.listdir(os.path.join(DATA_DIR, "historical_races"))):
    if fname.endswith(".json"):
        with open(os.path.join(DATA_DIR, "historical_races", fname)) as f:
            all_races.extend(json.load(f))
print(f"Loaded {len(all_races)} races")

# Try multiple cliff assumptions to see which gives consistent offsets
for cliff_label, CLIFFS in [
    ("S=8,M=17,H=20", {"SOFT": 8, "MEDIUM": 17, "HARD": 20}),
    ("S=10,M=20,H=30", {"SOFT": 10, "MEDIUM": 20, "HARD": 30}),
    ("S=5,M=12,H=18", {"SOFT": 5, "MEDIUM": 12, "HARD": 18}),
]:
    print(f"\n{'='*70}")
    print(f"CLIFFS: {cliff_label}")
    print(f"{'='*70}")

    # Find same-race driver pairs where BOTH have zero degradation
    # and different compound mixes
    zero_deg_pairs = []

    for race in all_races:
        cfg = race["race_config"]
        N = cfg["total_laps"]
        base = cfg["base_lap_time"]
        pit_t = cfg["pit_lane_time"]
        temp = cfg["track_temp"]
        fp = race["finishing_positions"]
        pos_map = {d: i for i, d in enumerate(fp)}

        # For each driver, check if ALL stints are below cliff
        drivers = []
        for key in race["strategies"]:
            s = race["strategies"][key]
            did = s["driver_id"]
            tire = s["starting_tire"]
            stops = sorted(s["pit_stops"], key=lambda x: x["lap"])
            stints = []
            prev = 0
            for ps in stops:
                stints.append((tire, ps["lap"] - prev))
                tire = ps["to_tire"]
                prev = ps["lap"]
            stints.append((tire, N - prev))

            # Check zero degradation
            all_below_cliff = all(l <= CLIFFS[c] for c, l in stints)
            if not all_below_cliff:
                continue

            # Compute compound laps
            S = sum(l for c, l in stints if c == "SOFT")
            M = sum(l for c, l in stints if c == "MEDIUM")
            H = sum(l for c, l in stints if c == "HARD")
            n_pits = len(stops)
            pos = pos_map[did]

            drivers.append({
                "did": did, "pos": pos, "pits": n_pits,
                "S": S, "M": M, "H": H, "stints": stints,
            })

        # Find pairs with same pit count, different compound mix
        for i in range(len(drivers)):
            for j in range(i + 1, len(drivers)):
                dA, dB = drivers[i], drivers[j]
                if dA["pits"] != dB["pits"]:
                    continue
                if dA["S"] == dB["S"] and dA["M"] == dB["M"] and dA["H"] == dB["H"]:
                    continue  # same compound mix

                # A finishes ahead of B?
                if dA["pos"] < dB["pos"]:
                    winner, loser = dA, dB
                else:
                    winner, loser = dB, dA

                zero_deg_pairs.append({
                    "N": N, "base": base, "pit": pit_t, "temp": temp,
                    "winner": winner, "loser": loser,
                })

    print(f"  Zero-deg same-pit pairs: {len(zero_deg_pairs)}")

    # Among these, find pairs where the compound difference is ONLY between
    # two compounds (e.g., winner has more SOFT, loser has more HARD, same MEDIUM)
    for c1, c2 in [("SOFT", "HARD"), ("SOFT", "MEDIUM"), ("MEDIUM", "HARD")]:
        c3 = [x for x in ["SOFT", "MEDIUM", "HARD"] if x not in (c1, c2)][0]
        relevant = []
        for p in zero_deg_pairs:
            w, l = p["winner"], p["loser"]
            # Third compound must be equal
            if w[c3[0]] != l[c3[0]]:
                continue
            d1 = w[c1[0]] - l[c1[0]]  # diff in c1 laps
            d2 = w[c2[0]] - l[c2[0]]  # diff in c2 laps
            if d1 == 0 and d2 == 0:
                continue
            # Since total laps = N and pits are same, d1 + d2 = 0 (what c1 gains, c2 loses)
            # Actually d1 + d2 + d3 = 0, and d3 = 0, so d1 = -d2
            if d1 + d2 != 0:
                continue  # shouldn't happen if d3=0
            relevant.append((p, d1, d2))

        if not relevant:
            print(f"\n  {c1} vs {c2}: no pure pairs found")
            continue

        print(f"\n  {c1} vs {c2}: {len(relevant)} pairs")
        print(f"  {'N':>3} {'base':>6} {'pit':>5} {'temp':>4} | "
              f"d_{c1[:1]}  d_{c2[:1]} | winner_beats_by | offset_{c1[:1]}-offset_{c2[:1]}")
        print(f"  {'-'*70}")

        # For each pair: time_winner < time_loser
        # time_W - time_L = offset[c1]*(W_c1 - L_c1) + offset[c2]*(W_c2 - L_c2) < 0
        # = offset[c1]*d1 + offset[c2]*d2 < 0
        # Since d1 = -d2: (offset[c1] - offset[c2]) * d1 < 0
        # If d1 > 0 (winner has MORE c1): offset[c1] < offset[c2]
        #   => c1 is faster (lower offset)
        # If d1 < 0 (winner has LESS c1): offset[c1] > offset[c2]

        # We can't get the exact VALUE from ordering alone,
        # but we can check sign consistency.
        # The offset difference per lap: we need actual time differences.

        # Actually, within a race, we know the ORDERING but not the time gap.
        # However, if winner is at position p and loser at position p+1,
        # they are ADJACENT, meaning the time gap is the smallest possible.
        # For non-adjacent pairs, we know other drivers are between them.

        offset_signs = defaultdict(int)
        for p, d1, d2 in relevant[:20]:
            w, l = p["winner"], p["loser"]
            gap = l["pos"] - w["pos"]
            if d1 > 0:
                sign = f"offset_{c1[:1]} < offset_{c2[:1]}"
            else:
                sign = f"offset_{c1[:1]} > offset_{c2[:1]}"
            offset_signs[sign] += 1
            if len(relevant) <= 20 or gap == 1:  # show adjacent or all if few
                print(f"  {p['N']:3d} {p['base']:6.1f} {p['pit']:5.1f} {p['temp']:4d} | "
                      f"{d1:+3d} {d2:+3d} | P{w['pos']+1}->P{l['pos']+1} (gap={gap}) | {sign}")

        print(f"\n  Summary: {dict(offset_signs)}")
        # Check if sign is consistent
        if len(offset_signs) == 1:
            print(f"  => 100% consistent: {list(offset_signs.keys())[0]}")
        else:
            total = sum(offset_signs.values())
            for s, c in sorted(offset_signs.items(), key=lambda x: -x[1]):
                print(f"  => {s}: {c}/{total} ({100*c/total:.1f}%)")
