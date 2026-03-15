"""Investigate temperature-dependent cliff pattern.

Key finding: HARD cliff appears to be 20 at temp 28-33, but much higher
at lower/higher temps. This suggests either:
1. cliff = f(temp)
2. deg_rate = f(temp) with non-linear temp dependence
3. Something else entirely

Let's find exact optimal pit laps as a function of temperature.
"""
import json, os, sys
from collections import defaultdict
sys.stdout.reconfigure(encoding='utf-8')

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

# Load ALL data
print("Loading data...")
all_races = []
for fname in sorted(os.listdir(os.path.join(DATA_DIR, "historical_races"))):
    if fname.endswith(".json"):
        with open(os.path.join(DATA_DIR, "historical_races", fname)) as f:
            all_races.extend(json.load(f))
print(f"Loaded {len(all_races)} races")

# For 1-stop HARD->MEDIUM transitions, find THE single best pit lap
# by comparing drivers who are direct competitors in the same race

# For each (N, base, pit, temp), collect all HARD->MEDIUM drivers
# and find who finishes best for each pit lap choice

# Build: (temp) -> list of (winner_pit_lap, loser_pit_lap) for same-race comparisons
comparisons_H = defaultdict(list)  # temp -> [(winning_pit, losing_pit), ...]
comparisons_S = defaultdict(list)
comparisons_M = defaultdict(list)

for race in all_races:
    cfg = race["race_config"]
    N = cfg["total_laps"]
    temp = cfg["track_temp"]
    fp = race["finishing_positions"]
    pos_map = {d: i for i, d in enumerate(fp)}

    # Group 1-stop drivers by compound transition
    hm_drivers = []  # HARD->MEDIUM
    sm_drivers = []  # SOFT->MEDIUM
    sh_drivers = []  # SOFT->HARD
    mh_drivers = []  # MEDIUM->HARD
    ms_drivers = []  # MEDIUM->SOFT
    hs_drivers = []  # HARD->SOFT

    for key in race["strategies"]:
        s = race["strategies"][key]
        did = s["driver_id"]
        stops = s["pit_stops"]
        if len(stops) != 1:
            continue
        ps = stops[0]
        from_t = s["starting_tire"]
        to_t = ps["to_tire"]
        pit_lap = ps["lap"]
        pos = pos_map[did]

        if from_t == "HARD" and to_t == "MEDIUM":
            hm_drivers.append((pit_lap, pos, did))
        elif from_t == "SOFT" and to_t == "MEDIUM":
            sm_drivers.append((pit_lap, pos, did))
        elif from_t == "SOFT" and to_t == "HARD":
            sh_drivers.append((pit_lap, pos, did))
        elif from_t == "MEDIUM" and to_t == "HARD":
            mh_drivers.append((pit_lap, pos, did))
        elif from_t == "MEDIUM" and to_t == "SOFT":
            ms_drivers.append((pit_lap, pos, did))
        elif from_t == "HARD" and to_t == "SOFT":
            hs_drivers.append((pit_lap, pos, did))

    # For each group, record pairwise comparisons
    for drivers, comp_dict in [
        (hm_drivers, comparisons_H),
        (sm_drivers, comparisons_S),
        (mh_drivers, comparisons_M),
    ]:
        for i in range(len(drivers)):
            for j in range(i+1, len(drivers)):
                if drivers[i][0] == drivers[j][0]:
                    continue  # same pit lap
                if drivers[i][1] < drivers[j][1]:
                    winner, loser = drivers[i], drivers[j]
                elif drivers[j][1] < drivers[i][1]:
                    winner, loser = drivers[j], drivers[i]
                else:
                    continue  # same position (shouldn't happen)
                comp_dict[temp].append((winner[0], loser[0], N))

# For HARD->MEDIUM, find optimal pit lap by temp
print("\n" + "="*70)
print("HARD->MEDIUM: Optimal pit lap by temperature")
print("="*70)
for temp in sorted(comparisons_H.keys()):
    comparisons = comparisons_H[temp]
    # Count wins by pit lap
    wins = defaultdict(int)
    losses = defaultdict(int)
    for w_pit, l_pit, N in comparisons:
        wins[w_pit] += 1
        losses[l_pit] += 1

    # Net wins
    net = {pl: wins.get(pl, 0) - losses.get(pl, 0) for pl in set(wins) | set(losses)}
    sorted_pits = sorted(net.items(), key=lambda x: -x[1])
    top5 = sorted_pits[:5]
    total_comps = len(comparisons)
    print(f"  temp={temp:2d}: {total_comps:5d} comparisons, top pits: {[(pl, n) for pl, n in top5]}")

print("\n" + "="*70)
print("SOFT->MEDIUM: Optimal pit lap by temperature")
print("="*70)
for temp in sorted(comparisons_S.keys()):
    comparisons = comparisons_S[temp]
    wins = defaultdict(int)
    losses = defaultdict(int)
    for w_pit, l_pit, N in comparisons:
        wins[w_pit] += 1
        losses[l_pit] += 1
    net = {pl: wins.get(pl, 0) - losses.get(pl, 0) for pl in set(wins) | set(losses)}
    sorted_pits = sorted(net.items(), key=lambda x: -x[1])
    top5 = sorted_pits[:5]
    total_comps = len(comparisons)
    print(f"  temp={temp:2d}: {total_comps:5d} comparisons, top pits: {[(pl, n) for pl, n in top5]}")

print("\n" + "="*70)
print("MEDIUM->HARD: Optimal pit lap by temperature")
print("="*70)
for temp in sorted(comparisons_M.keys()):
    comparisons = comparisons_M[temp]
    wins = defaultdict(int)
    losses = defaultdict(int)
    for w_pit, l_pit, N in comparisons:
        wins[w_pit] += 1
        losses[l_pit] += 1
    net = {pl: wins.get(pl, 0) - losses.get(pl, 0) for pl in set(wins) | set(losses)}
    sorted_pits = sorted(net.items(), key=lambda x: -x[1])
    top5 = sorted_pits[:5]
    total_comps = len(comparisons)
    print(f"  temp={temp:2d}: {total_comps:5d} comparisons, top pits: {[(pl, n) for pl, n in top5]}")

# CRITICAL: Show pit_lap preferences grouped by (N, temp) for H->M
# to see if it's really just temp or also depends on N
print("\n" + "="*70)
print("HARD->MEDIUM: Optimal by (N, temp)")
print("="*70)

hm_by_Ntemp = defaultdict(list)
for temp, comps in comparisons_H.items():
    for w_pit, l_pit, N in comps:
        hm_by_Ntemp[(N, temp)].append((w_pit, l_pit))

# Show for N=40 across temps
for N in [25, 30, 35, 40, 45, 50]:
    print(f"\n  N={N}:")
    for temp in sorted(set(t for (n, t) in hm_by_Ntemp if n == N)):
        comps = hm_by_Ntemp[(N, temp)]
        wins = defaultdict(int)
        losses = defaultdict(int)
        for w_pit, l_pit in comps:
            wins[w_pit] += 1
            losses[l_pit] += 1
        net = {pl: wins.get(pl, 0) - losses.get(pl, 0) for pl in set(wins) | set(losses)}
        sorted_pits = sorted(net.items(), key=lambda x: -x[1])
        top3 = sorted_pits[:3]
        total = len(comps)
        if total >= 5:
            print(f"    temp={temp:2d}: {total:4d} comps, best: {[(pl, n) for pl, n in top3]}")
