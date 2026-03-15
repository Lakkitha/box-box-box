"""Phase 0: Just load data and print stats."""
import json, os, time
DATA = os.path.join(os.path.dirname(__file__), "..", "data", "historical_races")
t0 = time.time()
with open(os.path.join(DATA, "races_00000-00999.json")) as f:
    races = json.load(f)
print(f"Loaded {len(races)} races in {time.time()-t0:.1f}s")
temps = [r["race_config"]["track_temp"] for r in races]
laps = [r["race_config"]["total_laps"] for r in races]
print(f"Temp: {min(temps)}-{max(temps)}, Laps: {min(laps)}-{max(laps)}")
