# Surf model (prototype)

Physics-based "spot filters" for California surf breaks, driven by live CDIP buoys.
Built and checked so far for the SF Bay Area; set up to grow region by region.

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
python validate.py bayarea 30         # check against nearshore buoys -> out/check_*.png
python plot_filters.py                # spot filter heatmaps -> out/spot_filters_<region>.png
```

## Adding spots and regions
- **Spot in an existing region:** add a row to `spots.csv` (`kind=spot`, `depth` = model point depth,
  10 m by default), then `fetch_bathy.py fine <slug>` and `build_tables.py <slug>`.
- **Check buoy:** a row with `kind=buoy` and the CDIP `station`; `validate.py` compares it with the model.
- **New region:** fill in its entry in `config.py` (box and deep-water input buoy; North Coast,
  Santa Cruz/Monterey, SLO and SoCal are sketched there but not built or checked),
  then `fetch_bathy.py coarse <region>` and add its spots.

## Files
- `config.py`, `spots.csv`: regions, input buoys, spots and check buoys
- `common.py`: bathymetry grids, projection, wave dispersion
- `raytrace.py`: ray tracer, nested 10 m → 90 m tracing, transfer tables (Longuet-Higgins S·c·cg conservation)
- `buoy.py`: CDIP fetch (latest and history) + Maximum Entropy directional spectrum
- `partition.py`: splits a spectrum into separate swells (watershed partitioning)
- `predict.py`: nowcast at each spot, per swell
- `ribbons.py`, `ribbons_template.html`: consumer-style page showing each swell's real refracted path into a spot
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
