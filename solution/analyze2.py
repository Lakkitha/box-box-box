"""Statistical summary of patterns in simple 1-stop races."""
import json
import os
from collections import Counter, defaultdict

COMPACT_PATH = os.path.join(os.path.dirname(__file__), "races_compact.json")
TIRE = ["SOFT", "MEDIUM", "HARD"]

with open(COMPACT_PATH) as f:
    all_races = json.load(f)

simple = [r for r in all_races
          if all(len(st) == 2 and np == 1 for _, st, np in r["d"])][:100]

print(f"Analyzing {len(simple)} simple 1-stop races\n")

# For each driver finishing position (1-20), tally:
#   - compound combo (stint1_tire -> stint2_tire)
#   - max stint length
#   - whether the longer stint was HARD
#   - stint balance (how even the two stints are)

combo_by_pos = defaultdict(Counter)     # pos -> combo -> count
max_stint_by_pos = defaultdict(list)    # pos -> [max_stint_len, ...]
longer_hard_by_pos = defaultdict(int)   # pos -> count where longest stint is HARD
balance_by_pos = defaultdict(list)      # pos -> [abs(l1-l2), ...]
soft_laps_by_pos = defaultdict(list)
hard_laps_by_pos = defaultdict(list)
med_laps_by_pos = defaultdict(list)

for r in simple:
    expected = r["e"]
    dinfo = {}
    for did, stints, _ in r["d"]:
        dinfo[did] = stints

    for pos, did in enumerate(expected):
        s1_tire, s1_len = dinfo[did][0]
        s2_tire, s2_len = dinfo[did][1]
        combo = f"{TIRE[s1_tire]}->{TIRE[s2_tire]}"
        combo_by_pos[pos][combo] += 1
        max_stint_by_pos[pos].append(max(s1_len, s2_len))
        balance_by_pos[pos].append(abs(s1_len - s2_len))

        longer_tire = s1_tire if s1_len >= s2_len else s2_tire
        if longer_tire == 2:  # HARD
            longer_hard_by_pos[pos] += 1

        # Count laps by compound
        for ti, sl in [(s1_tire, s1_len), (s2_tire, s2_len)]:
            if ti == 0:
                soft_laps_by_pos[pos].append(sl)
            elif ti == 1:
                med_laps_by_pos[pos].append(sl)
            else:
                hard_laps_by_pos[pos].append(sl)

# Print summary
print("=" * 80)
print(f"{'Pos':>3}  {'Top Combo':>20} {'2nd Combo':>20}  AvgMaxStint  AvgBalance  LongerHard%")
print("=" * 80)
for pos in range(20):
    combos = combo_by_pos[pos].most_common(2)
    c1 = f"{combos[0][0]}({combos[0][1]})" if combos else ""
    c2 = f"{combos[1][0]}({combos[1][1]})" if len(combos) > 1 else ""
    avg_max = sum(max_stint_by_pos[pos]) / len(max_stint_by_pos[pos])
    avg_bal = sum(balance_by_pos[pos]) / len(balance_by_pos[pos])
    lh_pct = longer_hard_by_pos[pos] / 100 * 100
    print(f"  {pos+1:>2}  {c1:>20} {c2:>20}  {avg_max:>11.1f}  {avg_bal:>10.1f}  {lh_pct:>10.0f}%")

# Average SOFT/MED/HARD laps by finishing position
print(f"\n{'='*80}")
print(f"{'Pos':>3}  AvgSoftLaps(n)   AvgMedLaps(n)    AvgHardLaps(n)")
print(f"{'='*80}")
for pos in range(20):
    sl = soft_laps_by_pos[pos]
    ml = med_laps_by_pos[pos]
    hl = hard_laps_by_pos[pos]
    s_avg = f"{sum(sl)/len(sl):.1f}({len(sl)})" if sl else "-(0)"
    m_avg = f"{sum(ml)/len(ml):.1f}({len(ml)})" if ml else "-(0)"
    h_avg = f"{sum(hl)/len(hl):.1f}({len(hl)})" if hl else "-(0)"
    print(f"  {pos+1:>2}  {s_avg:>15}  {m_avg:>15}  {h_avg:>15}")

# Look at SYMMETRIC pairs: same compounds, same lengths, different order
# e.g. HARD x25 -> MED x19  vs  MED x19 -> HARD x25
print(f"\n{'='*80}")
print("MIRROR PAIRS: same (tire1, len1, tire2, len2) vs reversed order")
print(f"{'='*80}")
mirror_wins = Counter()  # "A_first" vs "B_first"
mirror_count = 0
for r in simple:
    expected = r["e"]
    dinfo = {}
    for did, stints, _ in r["d"]:
        dinfo[did] = stints

    # Find mirror pairs
    drivers_by_key = defaultdict(list)
    for did in expected:
        s1t, s1l = dinfo[did][0]
        s2t, s2l = dinfo[did][1]
        # Normalize: sort by (tire, len) to find mirrors
        key = tuple(sorted([(s1t, s1l), (s2t, s2l)]))
        drivers_by_key[key].append((did, s1t, s1l, s2t, s2l))

    for key, group in drivers_by_key.items():
        if len(group) < 2:
            continue
        # Check if there's a true mirror (different stint orders)
        orders = set()
        for did, s1t, s1l, s2t, s2l in group:
            if s1t != s2t or s1l != s2l:  # skip identical stints
                orders.add((s1t, s1l, s2t, s2l))
        if len(orders) == 2:
            # True mirror pair found
            mirror_count += 1
            # Who finishes first?
            for did, s1t, s1l, s2t, s2l in group:
                pos = expected.index(did)
                order_label = f"{TIRE[s1t]}x{s1l}->{TIRE[s2t]}x{s2l}"
                if mirror_count <= 20:
                    print(f"  Race temp={r['t']} laps={r['n']}: {did} P{pos+1} = {order_label}")

print(f"\nTotal mirror pairs found: {mirror_count}")

# KEY QUESTION: for mirror pairs, does the order matter?
# If HARD->MED always beats MED->HARD (or vice versa), that tells us about degradation
print(f"\n{'='*80}")
print("MIRROR: Who wins - stint1=HARD or stint1=other? (same compounds, same lengths)")
print(f"{'='*80}")
hard_first_wins = 0
hard_first_total = 0
for r in simple:
    expected = r["e"]
    dinfo = {}
    for did, stints, _ in r["d"]:
        dinfo[did] = stints

    drivers_by_key = defaultdict(list)
    for did in expected:
        s1t, s1l = dinfo[did][0]
        s2t, s2l = dinfo[did][1]
        key = tuple(sorted([(s1t, s1l), (s2t, s2l)]))
        drivers_by_key[key].append((did, s1t, s1l, s2t, s2l))

    for key, group in drivers_by_key.items():
        if len(group) < 2:
            continue
        if key[0] == key[1]:
            continue  # same stints, skip
        # Find the two different orders
        order_a = None
        order_b = None
        for did, s1t, s1l, s2t, s2l in group:
            if (s1t, s1l) == key[0]:
                if order_a is None:
                    order_a = []
                order_a.append(expected.index(did))
            else:
                if order_b is None:
                    order_b = []
                order_b.append(expected.index(did))

        if order_a and order_b:
            best_a = min(order_a)
            best_b = min(order_b)
            # Which order has the harder tire first?
            t0, _ = key[0]
            t1, _ = key[1]
            if t0 > t1:  # key[0] is harder
                hard_first = "A"
            elif t1 > t0:
                hard_first = "B"
            else:
                continue  # same tire type, different lengths

            if hard_first == "A":
                hard_first_total += 1
                if best_a < best_b:
                    hard_first_wins += 1
            else:
                hard_first_total += 1
                if best_b < best_a:
                    hard_first_wins += 1

print(f"Hard-first wins: {hard_first_wins}/{hard_first_total}")
if hard_first_total > 0:
    print(f"Hard-first win rate: {hard_first_wins/hard_first_total:.1%}")
