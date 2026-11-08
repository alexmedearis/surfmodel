# Surf model (prototype)

Physics-based "spot filters" for California surf breaks, driven by live deep-water buoys
(CDIP, or NOAA NDBC). Regions so far: SF Bay Area (checked against a nearshore buoy) and
Santa Cruz / Monterey Bay (built, not yet checked). Set up to grow region by region.

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
python ribbons.py                     # interactive swell-ribbon map per spot -> out/ribbons_*.html
python ribbons.py --at "2026-11-07 06:00" stinson   # same, for the buoy reading nearest a UTC time
python validate.py bayarea 30         # check against nearshore buoys -> out/check_*.png
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
- `predict.py`: nowcast at each spot, per swell
- `ribbons.py`, `ribbons_template.html`: consumer-style page showing each swell's real refracted path into a spot,
  on a zoomable map, with a fan per swell showing which of its directions reach the spot
- `validate.py`: model vs nearshore buoys

## How well it does so far
SF Bar buoy (CDIP 142, 16 m deep), predicted from Point Reyes (CDIP 029), 30 days to 2026-11-07:
RMSE 0.8 ft, correlation 0.87, bias −0.3 ft. Using the Point Reyes reading as-is would be off by 3.6 ft.
SF Bar sits in open water, so this checks the regional part; it can't yet show whether the
10 m grids are right inside coves like Linda Mar (both grids score about the same there).

## Known limitations
- Ray theory ignores diffraction, so it under-predicts energy leaking into sheltered corners.
  The 10 m grids are smoothed to ~30 m because finer features don't bend swell-length waves.
- No wind, tide, currents or sandbars. Breaker heights use a generic formula and are **uncalibrated**.
- Nowcast only. Forecasts need WaveWatch III spectra as input instead of the buoy.
