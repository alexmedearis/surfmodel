# Bay Area surf model: prototype

Physics-based "spot filters" for SF-area breaks, driven by the live Point Reyes buoy.

**Pipeline:** NOAA seafloor depths → wave ray tracing (refraction, headland shadows, shoaling)
→ per-spot transfer table (direction × period) → apply to live CDIP 029 directional spectrum.

## Run
```
python -m venv .venv && .venv/bin/pip install numpy scipy matplotlib requests
.venv/bin/python fetch_bathy.py      # NOAA Coastal Relief Model, ~90 m (once)
.venv/bin/python build_tables.py     # ray-trace each spot (~2.5 min, once)
.venv/bin/python predict.py          # live nowcast + what-if scenarios
.venv/bin/python plot_rays.py        # refraction maps  -> out/
.venv/bin/python plot_filters.py     # spot filter heatmaps -> out/
```
Add spots in `common.py` (`SPOTS`), then rerun `build_tables.py`.

## Files
- `common.py`: bathymetry grid, projection, wave dispersion, spot list
- `raytrace.py`: ray tracer + transfer tables (backward rays, Longuet-Higgins S·c·cg conservation)
- `buoy.py`: CDIP buoy fetch + Maximum Entropy directional spectrum
- `predict.py`: nowcast at each spot

## Known limitations (prototype)
- 90 m bathymetry is too coarse for small coves (Linda Mar) and reefs (Mavericks). Next: CA Seafloor Mapping / NCEI CUDEM 1/9″ (~3 m).
- Ray theory ignores diffraction, so it slightly under-predicts energy sneaking into headland shadows.
- No wind, tide or sandbars. Breaking heights use a generic empirical formula and are **uncalibrated**:
  the directional pattern is the useful output, and absolute heights need session-log calibration.
- Nowcast only. Forecasts need WaveWatch III spectral output as input instead of the buoy.
