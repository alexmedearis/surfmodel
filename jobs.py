"""The scheduled jobs that keep the published data current. Each runs the same way on a laptop,
in the Docker image, and (later) as a Cloud Run Job on a schedule.

  python jobs.py hourly      current swells, surf height, lineup, wind, tide, rating     (every hour)
  python jobs.py forecast    7-day forecast from the newest WaveWatch III run            (every 6 hours)
  python jobs.py nightly     maps and the spot index                                     (once a day)
  python jobs.py all         everything: first run, or local development

Where it writes: --store, else the SURF_STORE setting, else out/data (see publish.py).
Exits non-zero if any spot failed, so the scheduler can flag it; the other spots still publish.
"""
import sys, time
from publish import publish, get_store, PRODUCTS

JOBS = {
    "hourly":   ("now", "lineup", "weather"),   # buoys report every 30-60 min; wind forecast hourly
    "forecast": ("forecast",),          # NOAA runs at 00/06/12/18 UTC, online ~5 h later
    "nightly":  ("map",),               # only changes when a spot's grids or tables are rebuilt
    "all":      PRODUCTS,
}

def main(argv):
    args = list(argv)
    store_spec = None
    if "--store" in args:
        i = args.index("--store"); store_spec = args[i + 1]; del args[i:i + 2]
    if len(args) != 1 or args[0] not in JOBS:
        sys.exit(__doc__)
    t0 = time.time()
    failed = publish(get_store(store_spec), JOBS[args[0]])
    print(f"{args[0]}: done in {time.time() - t0:.0f} s" + (f", FAILED: {', '.join(failed)}" if failed else ""))
    return 1 if failed else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
