"""Analytical script: find patterns in simple races."""
import json
import os
from collections import Counter

COMPACT_PATH = os.path.join(os.path.dirname(__file__), "races_compact.json")

with open(COMPACT_PATH) as f:
    all_races = json.load(f)

# Find simple races: all 20 drivers have exactly 1 pit stop (2 stints)
simple = []
for r in all_races:
    if all(len(stints) == 2 and npits == 1 for _, stints, npits in r["d"]):
        simple.append(r)

print(f"Simple races (all drivers 1-stop, 2 stints): {len(simple)}")
print(f"Using first 100.\n")
simple = simple[:100]

# For each race, show top 5 and bottom 5
TIRE = ["SOFT", "MEDIUM", "HARD"]

for i, r in enumerate(simple[:20]):
    print(f"{'='*70}")
    print(f"Race {i}: base={r['b']}  pit={r['p']}  temp={r['t']}  laps={r['n']}")
    print(f"{'='*70}")
    expected = r["e"]

    # Build driver info
    dinfo = {}
    for did, stints, npits in r["d"]:
        s1_tire, s1_len = stints[0]
        s2_tire, s2_len = stints[1]
        dinfo[did] = (s1_tire, s1_len, s2_tire, s2_len)

    print(f"  {'Pos':>3}  {'Driver':>6}  {'Stint1':>14}  {'Stint2':>14}  PitLap")
    for pos, did in enumerate(expected):
        t1, l1, t2, l2 = dinfo[did]
        pit_lap = l1  # pit after stint1
        print(f"  {pos+1:>3}  {did:>6}  {TIRE[t1]:>6} x{l1:<3}   {TIRE[t2]:>6} x{l2:<3}   {pit_lap}")
    print()
