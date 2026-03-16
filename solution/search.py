"""DE parameter search: 8 params, 500 races, full-ordering accuracy."""
import json, os, sys, time
import numpy as np
from scipy.optimize import differential_evolution
sys.stdout.reconfigure(encoding='utf-8')

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

# Load 500 races
print("Loading races...")
with open(os.path.join(DATA_DIR, "historical_races", "races_00000-00999.json")) as f:
    all_races = json.load(f)[:500]
print(f"Loaded {len(all_races)} races")

# Precompute
print("Preprocessing...")
MAX_STINT = 60  # max stint length we'll see

race_data = []
for race in all_races:
    cfg = race["race_config"]
    N = cfg["total_laps"]
    base = cfg["base_lap_time"]
    pit = cfg["pit_lane_time"]
    temp = cfg["track_temp"]
    fp = race["finishing_positions"]

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

        S_laps = sum(l for c, l in stints if c == "SOFT")
        M_laps = sum(l for c, l in stints if c == "MEDIUM")
        H_laps = sum(l for c, l in stints if c == "HARD")
        n_pits = len(stops)

        # Store stint details for deg computation
        soft_stints = [l for c, l in stints if c == "SOFT"]
        med_stints = [l for c, l in stints if c == "MEDIUM"]
        hard_stints = [l for c, l in stints if c == "HARD"]

        drivers.append({
            "id": did, "S": S_laps, "M": M_laps, "H": H_laps,
            "pits": n_pits,
            "soft_stints": soft_stints, "med_stints": med_stints, "hard_stints": hard_stints,
        })

    race_data.append({
        "base": base, "pit": pit, "temp": temp, "N": N,
        "drivers": drivers, "expected": fp,
    })

print("Ready.")

# Track progress
call_count = [0]
best_so_far = [0]
t0 = time.time()

def neg_accuracy(params):
    """Negative accuracy (to minimize)."""
    oS, oH, cS, cM, cH, rS, rM, rH, tb = params
    cS_int = int(round(cS))
    cM_int = int(round(cM))
    cH_int = int(round(cH))

    correct = 0
    for rd in race_data:
        base = rd["base"]
        pit = rd["pit"]
        temp = rd["temp"]
        tf = tb * temp

        scores = []
        for d in rd["drivers"]:
            t = base * rd["N"] + d["pits"] * pit
            t += oS * d["S"] + oH * d["H"]  # offsets (oM=0)

            # Degradation
            for l in d["soft_stints"]:
                k = max(0, l - cS_int)
                t += rS * tf * k * (k + 1) / 2
            for l in d["med_stints"]:
                k = max(0, l - cM_int)
                t += rM * tf * k * (k + 1) / 2
            for l in d["hard_stints"]:
                k = max(0, l - cH_int)
                t += rH * tf * k * (k + 1) / 2

            scores.append((t, d["id"]))

        scores.sort()
        predicted = [s[1] for s in scores]
        if predicted == rd["expected"]:
            correct += 1

    acc = correct / len(race_data)
    call_count[0] += 1

    if acc > best_so_far[0]:
        best_so_far[0] = acc
        elapsed = time.time() - t0
        print(f"  [eval {call_count[0]:5d}, {elapsed:5.0f}s] NEW BEST: {acc:.4f} ({correct}/500) "
              f"oS={oS:.4f} oH={oH:.4f} cS={cS:.1f} cM={cM:.1f} cH={cH:.1f} "
              f"rS={rS:.4f} rM={rM:.4f} rH={rH:.4f} tb={tb:.5f}")
        sys.stdout.flush()

    if call_count[0] % 500 == 0:
        elapsed = time.time() - t0
        print(f"  [eval {call_count[0]:5d}, {elapsed:5.0f}s] best={best_so_far[0]:.4f}")
        sys.stdout.flush()

    return -acc

bounds = [
    (-2.0, 0.0),     # oS
    (0.0, 2.0),      # oH
    (5.0, 12.0),     # cliff_S
    (12.0, 22.0),    # cliff_M
    (16.0, 25.0),    # cliff_H
    (0.01, 0.5),     # rate_S
    (0.01, 0.3),     # rate_M
    (0.01, 0.2),     # rate_H
    (0.001, 0.1),    # temp_b
]

print("\nStarting differential evolution...")
print(f"Bounds: {bounds}")
print(f"popsize=20, maxiter=100")

result = differential_evolution(
    neg_accuracy,
    bounds,
    popsize=20,
    maxiter=100,
    seed=42,
    tol=0.001,
    disp=False,
    workers=1,  # workers=-1 doesn't work with closures on Windows
)

print(f"\n{'='*70}")
print(f"DE RESULT")
print(f"{'='*70}")
print(f"Best accuracy: {-result.fun:.4f} ({int(-result.fun*500)}/500)")
oS, oH, cS, cM, cH, rS, rM, rH, tb = result.x
print(f"oS={oS:.6f}, oH={oH:.6f}")
print(f"cliff_S={cS:.2f} (~{int(round(cS))}), cliff_M={cM:.2f} (~{int(round(cM))}), cliff_H={cH:.2f} (~{int(round(cH))})")
print(f"rate_S={rS:.6f}, rate_M={rM:.6f}, rate_H={rH:.6f}")
print(f"temp_b={tb:.8f}")
print(f"temp_factor at temp=30: {tb*30:.6f}")
print(f"DE converged: {result.success}, message: {result.message}")
print(f"Evaluations: {result.nfev}")
print(f"Total time: {time.time()-t0:.0f}s")

# Validate on next 500 races
print(f"\n{'='*70}")
print("VALIDATION on races 500-999")
print(f"{'='*70}")
with open(os.path.join(DATA_DIR, "historical_races", "races_00000-00999.json")) as f:
    val_races_raw = json.load(f)[500:]

val_correct = 0
params = result.x
for race in val_races_raw:
    cfg = race["race_config"]
    N = cfg["total_laps"]
    base = cfg["base_lap_time"]
    pit = cfg["pit_lane_time"]
    temp = cfg["track_temp"]
    tf = params[8] * temp
    cSi, cMi, cHi = int(round(params[2])), int(round(params[3])), int(round(params[4]))

    scores = []
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

        t = base * N + len(stops) * pit
        for c, l in stints:
            if c == "SOFT":
                t += params[0] * l
                k = max(0, l - cSi)
                t += params[5] * tf * k * (k + 1) / 2
            elif c == "MEDIUM":
                k = max(0, l - cMi)
                t += params[6] * tf * k * (k + 1) / 2
            else:
                t += params[1] * l
                k = max(0, l - cHi)
                t += params[7] * tf * k * (k + 1) / 2
        scores.append((t, did))

    scores.sort()
    predicted = [s[1] for s in scores]
    if predicted == race["finishing_positions"]:
        val_correct += 1

print(f"Validation accuracy: {val_correct}/500 ({100*val_correct/500:.1f}%)")

# Test cases
print(f"\n{'='*70}")
print("TEST CASES")
print(f"{'='*70}")
test_ok = 0
test_tot = 0
for i in range(1, 101):
    inp = os.path.join(DATA_DIR, "test_cases", "inputs", f"test_{i:03d}.json")
    exp = os.path.join(DATA_DIR, "test_cases", "expected_outputs", f"test_{i:03d}.json")
    if not os.path.exists(inp):
        continue
    test_tot += 1
    with open(inp) as f:
        race = json.load(f)
    with open(exp) as f:
        expected = json.load(f)["finishing_positions"]

    cfg = race["race_config"]
    N = cfg["total_laps"]
    base = cfg["base_lap_time"]
    pit = cfg["pit_lane_time"]
    temp = cfg["track_temp"]
    tf = params[8] * temp

    scores = []
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

        t = base * N + len(stops) * pit
        for c, l in stints:
            if c == "SOFT":
                t += params[0] * l
                k = max(0, l - cSi)
                t += params[5] * tf * k * (k + 1) / 2
            elif c == "MEDIUM":
                k = max(0, l - cMi)
                t += params[6] * tf * k * (k + 1) / 2
            else:
                t += params[1] * l
                k = max(0, l - cHi)
                t += params[7] * tf * k * (k + 1) / 2
        scores.append((t, did))

    scores.sort()
    predicted = [s[1] for s in scores]
    if predicted == expected:
        test_ok += 1

print(f"Test accuracy: {test_ok}/{test_tot} ({100*test_ok/test_tot:.1f}%)")
print(f"\nTotal time: {time.time()-t0:.0f}s")
