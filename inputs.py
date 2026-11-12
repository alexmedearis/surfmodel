"""Fetch everything a region's products need for one run: the input buoy reading, its swells,
the forecast (scaled to the buoy) and the regional grid. Shared by ribbons.py (pages) and
publish.py (data files)."""
import datetime as dt
import config, forecast
from buoy import latest, nearest
from common import Bathy
from predict import swells

def load_forecast(region, spec, run=None):
    """The newest (or given) WaveWatch III run for the region, scaled to the buoy reading
    `spec`, from that reading onward; None (with a note) if NOAA's server can't be reached."""
    try:
        specs = forecast.load(region, run=run)
        gain = forecast.nudge(specs, spec)
        specs = [x for x in specs if x["time"] >= spec["time"] - dt.timedelta(hours=1.5)]
        fc = dict(specs=specs, parts=[swells(x) for x in specs], run=specs[0]["run"], gain=gain,
                  point=config.REGIONS[region]["forecast_point"])
        print(f"  forecast: WaveWatch III run {fc['run']:%Y-%m-%d %HZ}, {len(specs)} steps, "
              f"scaled x{gain:.2f} to match the buoy", flush=True)
        return fc
    except Exception as e:                           # the products still build without it
        print("  forecast unavailable:", e, flush=True)
        return None

def region_inputs(region, when=None, with_forecast=True, run=None):
    """dict(spec, parts, fc, coarse, live) for `region`: the latest buoy reading, or the one nearest
    `when` (aware UTC datetime; no forecast then, unless `run` names a cached one)."""
    stn = config.REGIONS[region]["input_buoy"]
    spec = nearest(stn, when) if when else latest(stn); spec["stn"] = stn
    print(f"{config.REGIONS[region]['name']}: buoy {stn} at {spec['time']:%Y-%m-%d %H:%M} UTC", flush=True)
    fc = load_forecast(region, spec, run) if with_forecast and (run or not when) else None
    # live: the latest reading, so today's wind and tide apply (not for replays of a past time)
    return dict(spec=spec, parts=swells(spec), fc=fc, coarse=Bathy.coarse(region), live=when is None)
