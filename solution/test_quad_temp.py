"""Test linear temp factor with per-compound rates.

Formula: lap_time = base + offset[c] + max(0, age - cliff[c]) * rate[c] * (a + b * temp)
"""
import json, os, sys
sys.stdout.reconfigure(encoding='utf-8')

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

with open(os.path.join(DATA_DIR, "historical_races", "races_00000-00999.json")) as f:
    races = json.load(f)[:200]

CLIFFS = {"SOFT": 8, "MEDIUM": 17, "HARD": 20}
OFFSETS = {"SOFT": 0, "MEDIUM": 0, "HARD": 0}
RATES = {"SOFT": 1.0, "MEDIUM": 0.7, "HARD": 0.5}

def predict_race(race, a, b):
    cfg = race["race_config"]
    N = cfg["total_laps"]
    base = cfg["base_lap_time"]
    pit = cfg["pit_lane_time"]
    temp = cfg["track_temp"]
    tf = a + b * temp

    times = []
    for key in race["strategies"]:
        s = race["strategies"][key]
        did = s["driver_id"]
        tire = s["starting_tire"]
        prev = 0
        stops = sorted(s["pit_stops"], key=lambda x: x["lap"])
        stints = []
        for ps in stops:
            stints.append((tire, ps["lap"] - prev))
            tire = ps["to_tire"]
            prev = ps["lap"]
        stints.append((tire, N - prev))

        total = base * N + len(stops) * pit
        for compound, length in stints:
            total += OFFSETS[compound] * length
            cliff = CLIFFS[compound]
            rate = RATES[compound]
            for lap in range(1, length + 1):
                if lap > cliff:
                    total += rate * tf * (lap - cliff)
        times.append((total, did))

    times.sort(key=lambda x: (x[0], x[1]))
    return [t[1] for t in times]

print("Formula: lap_time = base + offset[c] + max(0, age-cliff[c]) * rate[c] * (a + b*temp)")
print(f"Cliffs: {CLIFFS}")
print(f"Offsets: {OFFSETS}")
print(f"Rates: {RATES}")
print()

# Grid search a: 0.1 to 2.0 step 0.1, b: 0.01 to 0.20 step 0.01
results = []
for ai in range(1, 21):        # a = 0.1 to 2.0
    a = ai * 0.1
    for bi in range(1, 21):    # b = 0.01 to 0.20
        b = bi * 0.01
        correct = 0
        for race in races:
            pred = predict_race(race, a, b)
            actual = race["finishing_positions"]
            if pred == actual:
                correct += 1
        results.append((correct, a, b))

results.sort(reverse=True)
print("Top 5 (a, b) by accuracy:")
print(f"{'a':>6}  {'b':>6}  | Accuracy")
print("-" * 35)
for correct, a, b in results[:5]:
    print(f"{a:6.2f}  {b:6.3f}  | {correct}/200 ({100*correct/200:.1f}%)")
