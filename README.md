# Surf model (prototype)

Physics-based "spot filters" for California surf breaks, driven by live deep-water buoys
(CDIP, or NOAA NDBC) for right now and by NOAA's WaveWatch III swell forecast for the next 7 days. Regions so far: SF Bay Area (checked against a nearshore buoy) and
Santa Cruz / Monterey Bay (checked against a buoy inside the bay). Set up to grow region by region.

**Pipeline:** NOAA seafloor depths (~90 m regional grid + ~10 m nearshore grid per spot)
→ wave ray tracing (refraction, headland shadows, shoaling) → per-spot transfer table
(direction × period) → apply to the live deep-water buoy spectrum, split into separate swells.

## Run
```
pip install numpy scipy matplotlib requests pillow
python fetch_bathy.py fine            # ~10 m nearshore grid for each new spot in spots.csv
python build_tables.py                # ray-trace each new spot (~1-2 min each, in parallel)
python predict.py                     # live nowcast, broken down by swell; --what-if for scenarios
python plot_components.py             # today's swells traced into each spot -> out/components_*.png
python forecast.py santacruz          # NOAA WaveWatch III swell forecast at the region's input point
python ribbons.py                     # interactive swell-ribbon map + 7-day forecast per spot -> out/ribbons_*.html
python ribbons.py --at "2026-11-07 06:00" stinson   # same, for the buoy reading nearest a UTC time
python validate.py bayarea 30         # check against nearshore buoys -> out/check_*.png
python forecast_log.py                # record every forecast run still online (GitHub Actions does this every 6 h)
python score_forecast.py              # score the logged forecasts against the buoys, by days ahead
python plot_filters.py                # spot filter heatmaps -> out/spot_filters_<region>.png
```

## Adding spots and regions
- **Spot in an existing region:** add a row to `spots.csv` (`kind=spot`, `depth` = model point depth,
  10 m by default), then `fetch_bathy.py fine <slug>` and `build_tables.py <slug>`.
- **Check buoy:** a row with `kind=buoy` and the CDIP `station`; `validate.py` compares it with the model.
- **New region:** fill in its entry in `config.py` (box and deep-water input buoy; North Coast,
  SLO and SoCal are sketched there but not built or checked), then `fetch_bathy.py coarse <region>`
  and add its spots. The input buoy must be in open deep water, upwave of the region: for Santa Cruz
  that's NOAA 46042 (`ndbc:46042`), not CDIP 156, which sits inside Monterey Bay.
  `fetch_bathy.py` falls back to NOAA's combined DEM where the Coastal Relief Model service returns
  corrupt pixels (it does for Monterey Bay).

## Files
- `config.py`, `spots.csv`: regions, input buoys, spots and check buoys
- `common.py`: bathymetry grids, projection, wave dispersion
- `raytrace.py`: ray tracer, nested 10 m → 90 m tracing, transfer tables (Longuet-Higgins S·c·cg conservation)
- `buoy.py`: CDIP and NOAA NDBC fetch (latest, nearest to a time; history for CDIP) + Maximum Entropy directional spectrum
- `partition.py`: splits a spectrum into separate swells (watershed partitioning)
- `forecast.py`: NOAA WaveWatch III (GFS-Wave) forecast spectra at buoy locations, cached in `data/forecast/`,
  scaled to agree with the live buoy at the start
- `predict.py`: nowcast at each spot, per swell (takes a buoy reading or a forecast hour)
- `ribbons.py`, `ribbons_template.html`: consumer-style page showing each swell's real refracted path into a spot,
  on a zoomable map, with a fan per swell showing which of its directions reach the spot
- `validate.py`: model vs nearshore buoys
- `forecast_log.py`, `score_forecast.py`, `.github/workflows/forecast-log.yml`: forecast record and scoring.
  NOAA keeps only ~2 days of runs, so a GitHub Action logs each run (and recent buoy readings) to
  `data/forecast_log/` every 6 hours and commits it. Each run is scaled to the buoy reading from when it came out.

## How well it does so far
SF Bar buoy (CDIP 142, 16 m deep), predicted from Point Reyes (CDIP 029), 30 days to 2026-11-07:
RMSE 0.8 ft, correlation 0.87, bias −0.3 ft. Using the Point Reyes reading as-is would be off by 3.6 ft.
SF Bar sits in open water, so this checks the regional part; it can't yet show whether the
10 m grids are right inside coves like Linda Mar (both grids score about the same there).

Monterey Canyon buoy (CDIP 156, 133 m deep, inside Monterey Bay), predicted from NOAA 46042
(outside the bay), 30 days to 2026-11-08: RMSE 1.1 ft, correlation 0.82, bias −0.2 ft. Using the
46042 reading as-is would be off by 2.9 ft (+2.5 ft bias), so the model captures the bay's shelter.
Misses: ~3 ft low around Oct 24 (a swell the bay was more open to than the model thought) and
2-4 ft high at the Nov 7-8 peak. Like SF Bar, this checks the regional grid, not the 10 m spot grids.

Forecast (NOAA WaveWatch III, run through the same transfer tables), scored against the buoys
for 7 runs from Nov 7-8 2026, up to 3 days ahead. That's ~2 days of one storm, so treat it as a first look:
WaveWatch III came in 20-30% low offshore at 46042 during the Nov 7-8 peak. Scaling it to the live buoy
at the start (correction fading over ~24 h) brought CDIP 156 errors from 2.1 to 0.9 ft RMSE on day 1 and
from 1.4 to 0.9 ft on days 2-3. At SF Bar it was already good (1.0-1.2 ft; WaveWatch III's own nearshore
point there: 2.2 ft), and the scaling made it slightly worse (1.2-1.4 ft), because there WaveWatch III's low
bias had been cancelling a small high bias of ours. Needs a longer record: that's what the forecast log is for (`score_forecast.py`).

## Known limitations
- Ray theory ignores diffraction, so it under-predicts energy leaking into sheltered corners.
  The 10 m grids are smoothed to ~30 m because finer features don't bend swell-length waves.
- No wind, tide, currents or sandbars. Breaker heights use a generic formula and are **uncalibrated**.
- The forecast is swell only (no wind or tide yet). WaveWatch III's 10° direction bins are coarser than a
  buoy's, and NOAA keeps only ~2 days of runs online, so scoring the forecast relies on our own log (`forecast_log.py`).
