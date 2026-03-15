"""
Comprehensive parameter search - vectorized cliff grid + lstsq.
Tests wide cliff ranges, both PCT and FLAT offset models.
"""
import json, os, sys, time
import numpy as np
sys.stdout.reconfigure(encoding='utf-8')

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
MAX_CLIFF = 50

# ── Load data ───────────────────────────────────────────────────────────
print("Loading data...")
t0 = time.time()
all_races = []
for i in range(0, 5000, 1000):
    fn = f"races_{i:05d}-{i+999:05d}.json"
    with open(os.path.join(DATA_DIR, "historical_races", fn)) as f:
        all_races.extend(json.load(f))
print(f"Loaded {len(all_races)} races in {time.time()-t0:.1f}s")

N_TRAIN = 2000
train_races = all_races[:N_TRAIN]

# ── Precompute ──────────────────────────────────────────────────────────
print("Preprocessing...")
t0 = time.time()

race_info = []
for race in train_races:
    cfg = race["race_config"]
    N = cfg["total_laps"]
    base = cfg["base_lap_time"]
    pit = cfg["pit_lane_time"]
    temp = cfg["track_temp"]
    exp = race["finishing_positions"]
    pos_map = {d: i for i, d in enumerate(exp)}

    drivers = []
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

        Sl = sum(l for c, l in stints if c == "SOFT")
        Ml = sum(l for c, l in stints if c == "MEDIUM")
        Hl = sum(l for c, l in stints if c == "HARD")

        degS = np.zeros(MAX_CLIFF + 1)
        degM = np.zeros(MAX_CLIFF + 1)
        degH = np.zeros(MAX_CLIFF + 1)
        for c, l in stints:
            for cliff in range(MAX_CLIFF + 1):
                k = max(0, l - cliff)
                ds = k * (k + 1) / 2.0
                if c == "SOFT": degS[cliff] += ds
                elif c == "MEDIUM": degM[cliff] += ds
                else: degH[cliff] += ds

        drivers.append({
            "id": did, "pos": pos_map[did],
            "S": Sl, "M": Ml, "H": Hl, "pits": len(stops),
            "degS": degS, "degM": degM, "degH": degH,
        })

    drivers.sort(key=lambda d: d["pos"])
    race_info.append({"base": base, "pit": pit, "temp": temp, "N": N, "drivers": drivers})

print(f"Preprocessed in {time.time()-t0:.1f}s")

# ── Build pairwise arrays ──────────────────────────────────────────────
print("Building pair arrays...")
t0 = time.time()

pair_data = []
for ri, rd in enumerate(race_info):
    for p in range(len(rd["drivers"]) - 1):
        pair_data.append((ri, rd["drivers"][p], rd["drivers"][p + 1]))

NP = len(pair_data)
p_base = np.zeros(NP)
p_dS = np.zeros(NP)
p_dH = np.zeros(NP)
p_rhs = np.zeros(NP)
p_temp = np.zeros(NP)
p_ddegS = np.zeros((NP, MAX_CLIFF + 1))
p_ddegM = np.zeros((NP, MAX_CLIFF + 1))
p_ddegH = np.zeros((NP, MAX_CLIFF + 1))

for idx, (ri, d1, d2) in enumerate(pair_data):
    rd = race_info[ri]
    p_base[idx] = rd["base"]
    p_dS[idx] = d1["S"] - d2["S"]
    p_dH[idx] = d1["H"] - d2["H"]
    p_rhs[idx] = -(d1["pits"] - d2["pits"]) * rd["pit"]
    p_temp[idx] = rd["temp"]
    p_ddegS[idx] = d1["degS"] - d2["degS"]
    p_ddegM[idx] = d1["degM"] - d2["degM"]
    p_ddegH[idx] = d1["degH"] - d2["degH"]

p_base_dS = p_base * p_dS
p_base_dH = p_base * p_dH
print(f"  {NP} pairs in {time.time()-t0:.1f}s")


def eval_accuracy(w, cS, cM, cH, rd_list, pct=True):
    correct = 0
    for rd in rd_list:
        base = rd["base"]
        pit = rd["pit"]
        temp = rd["temp"]
        scores = []
        for d in rd["drivers"]:
            if pct:
                sc = base * d["S"] * w[0] + base * d["H"] * w[1]
            else:
                sc = d["S"] * w[0] + d["H"] * w[1]
            sc += (d["degS"][cS] * w[2] + temp * d["degS"][cS] * w[3] +
                   d["degM"][cM] * w[4] + temp * d["degM"][cM] * w[5] +
                   d["degH"][cH] * w[6] + temp * d["degH"][cH] * w[7] +
                   d["pits"] * pit)
            scores.append((sc, d["id"]))
        scores.sort()
        predicted = [s[1] for s in scores]
        actual = [d["id"] for d in rd["drivers"]]
        if predicted == actual:
            correct += 1
    return correct


# ── Cliff grid search ──────────────────────────────────────────────────
print("\n" + "=" * 70)
print("CLIFF GRID SEARCH")
print("=" * 70)
t0 = time.time()

cS_range = list(range(3, 20))   # 17
cM_range = list(range(10, 30))  # 20
cH_range = list(range(15, 42))  # 27
total = len(cS_range) * len(cM_range) * len(cH_range)
print(f"Search space: {total} combos")

best_pct_acc = 0
best_pct_cfg = None
best_flat_acc = 0
best_flat_cfg = None
top_pct = []
top_flat = []

count = 0
for cS in cS_range:
    t_cS = time.time()
    local_best_p = 0
    local_best_f = 0

    for cM in cM_range:
        for cH in cH_range:
            count += 1
            ddS = p_ddegS[:, cS]
            ddM = p_ddegM[:, cM]
            ddH = p_ddegH[:, cH]

            # PCT model
            A = np.column_stack([p_base_dS, p_base_dH,
                                 ddS, p_temp * ddS, ddM, p_temp * ddM, ddH, p_temp * ddH])
            w, _, _, _ = np.linalg.lstsq(A, p_rhs, rcond=None)
            corr = eval_accuracy(w, cS, cM, cH, race_info, pct=True)
            acc = corr / N_TRAIN
            if acc > best_pct_acc:
                best_pct_acc = acc
                best_pct_cfg = (cS, cM, cH, w.copy())
                print(f"  PCT: cS={cS} cM={cM} cH={cH} acc={acc:.4f} ({corr}/{N_TRAIN})")
            if acc > 0.05:
                top_pct.append((acc, cS, cM, cH))
            local_best_p = max(local_best_p, acc)

            # FLAT model
            A2 = np.column_stack([p_dS, p_dH,
                                  ddS, p_temp * ddS, ddM, p_temp * ddM, ddH, p_temp * ddH])
            w2, _, _, _ = np.linalg.lstsq(A2, p_rhs, rcond=None)
            corr2 = eval_accuracy(w2, cS, cM, cH, race_info, pct=False)
            acc2 = corr2 / N_TRAIN
            if acc2 > best_flat_acc:
                best_flat_acc = acc2
                best_flat_cfg = (cS, cM, cH, w2.copy())
                print(f"  FLAT: cS={cS} cM={cM} cH={cH} acc={acc2:.4f} ({corr2}/{N_TRAIN})")
            if acc2 > 0.05:
                top_flat.append((acc2, cS, cM, cH))
            local_best_f = max(local_best_f, acc2)

    print(f"  cS={cS}: pct_best={local_best_p:.4f} flat_best={local_best_f:.4f} [{time.time()-t_cS:.1f}s, {100*count/total:.0f}%]")

print(f"\nGrid search: {time.time()-t0:.0f}s")

# ── Results ─────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("RESULTS")
print("=" * 70)

for label, cfg, tops in [("PCT", best_pct_cfg, top_pct), ("FLAT", best_flat_cfg, top_flat)]:
    if cfg is None:
        print(f"\n{label}: No results"); continue
    cS, cM, cH, w = cfg
    acc = eval_accuracy(w, cS, cM, cH, race_info, pct=(label == "PCT")) / N_TRAIN
    print(f"\n{label}: cS={cS} cM={cM} cH={cH} acc={acc:.4f}")
    print(f"  w={w}")
    if abs(w[2]) > 1e-10 and abs(w[4]) > 1e-10 and abs(w[6]) > 1e-10:
        print(f"  Temp ratios: S={w[3]/w[2]:.6f} M={w[5]/w[4]:.6f} H={w[7]/w[6]:.6f}")
    tops.sort(reverse=True)
    print(f"  Top 15:")
    for i, (a, cs, cm, ch) in enumerate(tops[:15]):
        print(f"    {i+1}. acc={a:.4f} cS={cs} cM={cm} cH={ch}")

# ── Test cases ──────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("TEST CASES")
print("=" * 70)

for label, cfg in [("PCT", best_pct_cfg), ("FLAT", best_flat_cfg)]:
    if cfg is None: continue
    cS, cM, cH, w = cfg
    ok = tot = 0
    for i in range(1, 101):
        inp = os.path.join(DATA_DIR, "test_cases", "inputs", f"test_{i:03d}.json")
        exp = os.path.join(DATA_DIR, "test_cases", "expected_outputs", f"test_{i:03d}.json")
        if not os.path.exists(inp): continue
        tot += 1
        with open(inp) as f: race = json.load(f)
        with open(exp) as f: expected = json.load(f)["finishing_positions"]
        cfg2 = race["race_config"]
        base, pit, temp, N = cfg2["base_lap_time"], cfg2["pit_lane_time"], cfg2["track_temp"], cfg2["total_laps"]
        times = {}
        for key in race["strategies"]:
            s = race["strategies"][key]
            did = s["driver_id"]
            tire = s["starting_tire"]
            prev = 0; stops = sorted(s["pit_stops"], key=lambda x: x["lap"]); stints = []
            for ps in stops:
                stints.append((tire, ps["lap"] - prev)); tire = ps["to_tire"]; prev = ps["lap"]
            stints.append((tire, N - prev))
            Sl = sum(l for c, l in stints if c == "SOFT")
            Hl = sum(l for c, l in stints if c == "HARD")
            dSv = sum(max(0, l-cS)*(max(0, l-cS)+1)/2 for c, l in stints if c == "SOFT")
            dMv = sum(max(0, l-cM)*(max(0, l-cM)+1)/2 for c, l in stints if c == "MEDIUM")
            dHv = sum(max(0, l-cH)*(max(0, l-cH)+1)/2 for c, l in stints if c == "HARD")
            sc = (base*Sl*w[0]+base*Hl*w[1]) if label=="PCT" else (Sl*w[0]+Hl*w[1])
            sc += dSv*w[2]+temp*dSv*w[3]+dMv*w[4]+temp*dMv*w[5]+dHv*w[6]+temp*dHv*w[7]+len(stops)*pit
            times[did] = sc
        predicted = sorted(times.keys(), key=lambda d: (times[d], d))
        if predicted == expected: ok += 1
    print(f"  {label}: {ok}/{tot} ({100*ok/tot:.1f}%)")

print(f"\nTotal: {time.time()-t0:.0f}s")
