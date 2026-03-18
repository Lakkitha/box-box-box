"""Preprocess all 30 historical race files into a compact format for fast loading."""
import json
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "historical_races")
OUT_PATH = os.path.join(os.path.dirname(__file__), "races_compact.json")

TIRE_IDX = {"SOFT": 0, "MEDIUM": 1, "HARD": 2}

def compact_race(race):
    cfg = race["race_config"]
    drivers = []
    for strat in race["strategies"].values():
        tire = strat["starting_tire"]
        pit_map = {ps["lap"]: ps["to_tire"] for ps in strat["pit_stops"]}
        num_pits = len(strat["pit_stops"])

        # Build stints: list of [tire_index, stint_length]
        stints = []
        stint_tire = TIRE_IDX[tire]
        stint_len = 0
        for lap in range(1, cfg["total_laps"] + 1):
            stint_len += 1
            if lap in pit_map:
                stints.append([stint_tire, stint_len])
                stint_tire = TIRE_IDX[pit_map[lap]]
                stint_len = 0
        stints.append([stint_tire, stint_len])

        drivers.append([strat["driver_id"], stints, num_pits])

    return {
        "b": cfg["base_lap_time"],
        "p": cfg["pit_lane_time"],
        "t": cfg["track_temp"],
        "n": cfg["total_laps"],
        "d": drivers,
        "e": race["finishing_positions"],
    }

def main():
    files = sorted(os.listdir(DATA_DIR))
    print(f"Processing {len(files)} files...")
    all_compact = []
    for fn in files:
        with open(os.path.join(DATA_DIR, fn)) as f:
            races = json.load(f)
        for r in races:
            all_compact.append(compact_race(r))
        print(f"  {fn}: {len(races)} races")

    print(f"\nTotal races: {len(all_compact)}")
    with open(OUT_PATH, "w") as f:
        json.dump(all_compact, f, separators=(",", ":"))

    size = os.path.getsize(OUT_PATH)
    print(f"Written to {OUT_PATH}")
    print(f"Size: {size / 1024 / 1024:.2f} MB")

if __name__ == "__main__":
    main()
