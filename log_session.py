"""Log a surf session, for calibrating the model (see sessions.py).

  python log_session.py <spot> <time> <size> [--peel right|left|both|closeout|none]
                        [--quality 1-5] [--note "..."] [--utc]
  python log_session.py --list

  time: local California time, e.g. 7:30am, 16:00, "yesterday 4pm", "2026-11-09 07:30"
  size: how big the SETS were, on you: ankle, knee, thigh, waist, stomach, chest, shoulder,
        head, overhead, well-overhead, double-overhead, triple-overhead (or a number of feet,
        face height)

  e.g.  python log_session.py pleasure-point 7:30am head --peel right --quality 4
"""
import sys, argparse
import sessions

def main():
    if "--list" in sys.argv:
        rows = sessions.load()
        for r in rows:
            pred = f"model {r['pred_surf_lo_ft']}-{r['pred_surf_hi_ft']} ft" if r.get("pred_surf_hi_ft") else "no prediction"
            peel = f", peel {r['peel'] or '?'} (model {r['pred_peel'] or '?'})" if r.get("peel") or r.get("pred_peel") else ""
            print(f"{r['time']}  {r['spot']:16s} {r['size']:>16s} = {float(r['face_ft']):4.1f} ft  | {pred}{peel}")
        print(f"{len(rows)} sessions in {sessions.PATH}")
        return
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spot"); ap.add_argument("time"); ap.add_argument("size")
    ap.add_argument("--peel", default=""); ap.add_argument("--quality", default=""); ap.add_argument("--note", default="")
    ap.add_argument("--utc", action="store_true"); ap.add_argument("--no-peel-model", action="store_true")
    a = ap.parse_args()
    try:
        when = sessions.parse_time(a.time, a.utc)
        row = sessions.add(a.spot, when, a.size, a.peel, a.quality, a.note, with_peel=not a.no_peel_model)
    except ValueError as e:
        sys.exit(f"error: {e}")
    print(f"Logged {row['spot']} at {row['time']}: sets {row['size']} ({row['face_ft']} ft faces)")
    if row.get("pred_surf_hi_ft"):
        print(f"  the model said {row['pred_surf_lo_ft']}-{row['pred_surf_hi_ft']} ft"
              + (f", peeling {row['pred_peel']} ({row['pred_peel_angle']}°)" if row.get("pred_peel") else "")
              + f"  [{row['pred_main']}, buoy {row['buoy']} at {row['buoy_time']}]")

if __name__ == "__main__":
    main()
