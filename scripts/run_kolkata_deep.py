"""
Kolkata deep research - the full pipeline, chained and resumable.

  1. HARVEST   geo sweep across every Kolkata neighbourhood, landmark and WB
               district (134 place queries), 8 pages each. Also hashtags and the
               chaining graph from verified seeds. Writes leads + geo evidence.
  2. AUDIT     exact follower counts for pending leads, most-corroborated first,
               pre-filtered on post likes so civilians are skipped for free.
  3. DEEP SCAN 90 days of each verified creator's posts: partnerships, brands,
               metrics, content category, email.
  4. EXPORT    deliverables/Kolkata_Creators_Deep_Research.xlsx

Every phase saves as it goes. Re-running skips what is done.
  python scripts/run_kolkata_deep.py
  python scripts/run_kolkata_deep.py --from audit      (skip harvest)
  python scripts/run_kolkata_deep.py --from deepscan
"""
import sys, os, subprocess, time
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE)
PY = sys.executable

PHASES = [
    ("harvest", [PY, "-u", "core/regional_engine.py", "harvest", "--region", "kolkata",
                 "--sources", "geo,hashtag,chaining", "--pages", "8", "--hops", "2"]),
    ("audit", [PY, "-u", "core/regional_engine.py", "audit", "--region", "kolkata",
               "--limit", "1500", "--min-post-likes", "150"]),
    ("deepscan", [PY, "-u", "core/regional_engine.py", "deepscan", "--region", "kolkata",
                  "--limit", "400", "--days", "90", "--pause", "1.2"]),
    ("export", [PY, "-u", "core/regional_engine.py", "deepexport", "--region", "kolkata",
                "--xlsx", "Kolkata_Creators_Deep_Research.xlsx"]),
]

start_from = sys.argv[sys.argv.index("--from") + 1] if "--from" in sys.argv else "harvest"
started = False
for name, cmd in PHASES:
    if name == start_from:
        started = True
    if not started:
        continue
    print("\n" + "#" * 78)
    print(f"# PHASE {name.upper()}   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("#" * 78, flush=True)
    t0 = time.time()
    rc = subprocess.call(cmd)
    print(f"\n# {name} finished rc={rc} in {(time.time() - t0) / 60:.0f} min", flush=True)
    if rc != 0 and name != "export":
        print(f"# {name} exited non-zero; continuing to next phase with whatever was saved")
print("\n# ALL PHASES DONE", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
