# Surf model (prototype)

Physics-based "spot filters" for California surf breaks, driven by live deep-water buoys
(CDIP, or NOAA NDBC) for right now and by NOAA's WaveWatch III swell forecast for the next 7 days. Regions so far: SF Bay Area (Linda Mar, Ocean Beach, Mavericks, Stinson, Princeton Jetty) (checked against a nearshore buoy) and
Santa Cruz / Monterey Bay (checked against a buoy inside the bay). Set up to grow region by region.

**Pipeline:** NOAA seafloor depths (~90 m regional grid + ~10 m nearshore grid per spot)
→ wave ray tracing (refraction, headland shadows, shoaling) → per-spot transfer table
(direction × period) → apply to the live deep-water buoy spectrum, split into separate swells.

## Run
`make help` lists the everyday tasks: `make dev` publishes fresh data and runs the website at
http://localhost:8000; `make hourly` / `forecast` / `nightly` run one scheduled job; `make docker-hourly`
(etc.) runs it inside the Docker image instead, the way it will run in the cloud.
```
pip install -r requirements-dev.txt
python fetch_bathy.py fine            # ~10 m nearshore grid for each new spot in spots.csv
python build_tables.py                # ray-trace each new spot (~1-2 min each, in parallel)
python predict.py                     # live nowcast, broken down by swell; --what-if for scenarios
python plot_components.py             # today's swells traced into each spot -> out/components_*.png
python forecast.py santacruz          # NOAA WaveWatch III swell forecast at the region's input point
python ribbons.py                     # interactive swell-ribbon map + 7-day forecast per spot -> out/ribbons_*.html
python publish.py                     # the same data as files for the website/app -> out/data/v1/spots/<slug>/
python serve.py                       # the website, reading those files -> http://localhost:8000
python jobs.py hourly                 # a scheduled job: hourly (now + lineup), forecast (6-hourly), nightly (maps), all
python ribbons.py --at "2026-11-07 06:00" stinson   # same, for the buoy reading nearest a UTC time
python validate.py bayarea 30         # check against nearshore buoys -> out/check_*.png
python check_mop.py                   # check each spot's 10 m grid against CDIP's MOP nearshore model -> out/check_mop.png
python forecast_log.py                # record every forecast run still online (GitHub Actions does this every 6 h)
python score_forecast.py              # score the logged forecasts against the buoys, by days ahead
python log_session.py pleasure-point 7:30am head --peel right --quality 4   # log a session (sets, on you)
python calibrate.py                   # fit per-spot surf-height corrections from sessions -> data/calibration.json
python plot_filters.py                # spot filter heatmaps -> out/spot_filters_<region>.png
```

## Environments and deploying
The same code and Docker image run in four places; `deploy/<env>.env` holds each one's settings.

| | data written by | website served by | data read from |
|---|---|---|---|
| local | `make publish` (Python) | `make serve` (:8000) | `out/data` |
| emulator | `make emulator-job` (Docker) | `make emulators` (:5050, UI :4000) | Firebase Storage emulator |
| staging / prod | Cloud Run Jobs on Cloud Scheduler | Firebase Hosting | Firebase Storage |

- **Emulators**: `make emulators` starts the Firebase emulators (Storage, Hosting, Auth, Firestore) in Docker,
  then `make emulator-job JOB=all` publishes into them. The project id `demo-surf` can't reach a real project.
  Emulated data is kept in `.emulator-data/` between runs.
- **Cloud**: for now there's one Firebase project, production (`deploy/prod.env`), on the Blaze plan with
  Storage and Hosting started in the console; the emulators are the testing ground. `make cloud-setup` once,
  `make deploy` for each release (only from a committed tree), `make cloud-job JOB=all` to fill it right away.
  A separate staging project (`deploy/staging.env`, `ENV=staging`) gets added with accounts and payments,
  when a mistake could affect paying customers.
- The jobs: `surf-hourly` (:10 past each hour), `surf-forecast` (05:40, 11:40, 17:40, 23:40 UTC),
  `surf-nightly` (10:20 UTC), each 2 CPU / 2 GB (a full run peaks around 0.7 GB and takes ~1.5 min).
- Data is public-read under `v1/` (`firebase/storage.rules`); that's where paid access gets enforced later.
- The forecast log still runs as a GitHub Action (`.github/workflows/forecast-log.yml`).

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
- `products/`: what the model publishes per spot, as plain data, split by how often it changes:
  `spot_map` (coastline, depth, views; once per spot), `spot_now` (current swells, their paths and fans, surf
  height; per buoy reading), `spot_lineup` (the "In the water" wave field), `spot_forecast` (7-day series;
  per forecast run). `geometry.py` has the map frame and swell-path tracing; `page.py` assembles the pieces into
  the object the HTML page reads. None of them write files, so the same functions will feed the website's
  data files (and later a mobile app). `insights.py` turns them into short facts every client can show the
  same way: the spot's swell window (in `map.json` as `facts`) and what today's swells do there (main swell,
  arrival angle, favors lefts/rights, peel side and speed, swell mix; in `now.json` as `insights`).
- `web/`: the website. `index.html` lists the spots; `spot.html?spot=<slug>` shows one. `js/data.js` fetches
  the spot's published files and assembles the page's data; `js/common.js`, `map.js`, `forecast.js` and
  `lineup.js` draw it; `config.js` says where the data lives. `serve.py` runs it locally.
- `ribbons.py`: builds single-file spot pages (out/ribbons_*.html, open without a server) from `products/`,
  using the website's page with its CSS and scripts inlined, so there's one copy of the page code
- `publish.py`, `inputs.py`: write each spot's products as files (`map.json`, `now.json`, `forecast.json`,
  `lineup.json` + `lineup.bin`, plus `spots/index.json` and `spots/conditions.json`, every spot's current
  surf for the spot list) under a versioned `v1/` path, through a storage
  layer that's a local folder now (Google Cloud Storage at deploy time, picked with `--store` / `SURF_STORE`).
  `--only now,lineup` publishes just some products, for scheduling them separately. `load_spot()` reads a spot
  back the way the website will. `inputs.py` fetches a region's buoy reading and forecast for both scripts.
- `jobs.py`: the scheduled jobs (`hourly`, `forecast`, `nightly`, `all`) on top of `publish.py`. A spot
  that fails is skipped and reported (non-zero exit) so the others still publish.
- `firebase.json`, `firebase/` (rules, emulator image), `docker-compose.yml`, `deploy/` (environment settings,
  `build_web.py`, `setup.sh`, `deploy.sh`): Firebase and Google Cloud, see "Environments and deploying"
- `Dockerfile`, `requirements.txt`, `Makefile`: one image with the model, its data and the jobs; the job name
  is the argument and `SURF_STORE` says where to write (`docker run -v "$PWD/out/data:/data" surfmodel hourly`).
- `tests/snapshot.py`: regression check: rebuilds every spot from fixed inputs and compares with a recording
  (`save <dir>` / `check <dir>`; `check-published <dir> <tmp>` goes through the published files and back),
  so refactors can't silently change what's published
- `lineup.py`: real-geometry lineup for the "In the water" view. Forward rays from deep water over the spot's
  ~10 m grid (five directions across the swell's spread) give crest positions, heights, set arrival times and
  where each size of wave breaks; the break line's angle to the crest is the peel angle (Walker 1974, Hutt et
  al. 2001). The `break` column in spots.csv (point / reef / beach) decides whether the page claims a peel
  direction: beach breaks depend on sandbars, which no public data has.
- `validate.py`: model vs nearshore buoys
- `check_mop.py`: model vs CDIP's MOP nearshore model at each spot (the `mop` column in spots.csv)
- `sessions.py`, `log_session.py`, `calibrate.py`: surf session reports ("how was it?") and calibration.
  `sessions.py` is the shared core (schema, size scale, storage, the model's prediction for a spot and time),
  meant to be reused by the web/iPhone app backend; `log_session.py` is the command line for now. Each report
  stores the model's prediction when it was logged, so calibration doesn't need old buoy data.
  Sessions live in `data/sessions/sessions.csv`, which is **not committed** (where and when you surf).
  `calibrate.py` fits each spot's reported/predicted set height, shrunk toward 1 with few sessions (none
  below 3), and checks peel direction; `predict.surf_ft()` applies it everywhere and pages say "tuned to N sessions".
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

Spot level, against CDIP's MOP model (hourly wave height every ~100 m along the coast at 10-15 m
depth, computed independently with different methods and bathymetry), at the MOP point nearest each
spot, 30 days to 2026-11-09:

| Spot | MOP point | ours / MOP | RMSE | r |
|---|---|---|---|---|
| Linda Mar | SM376 | 0.94 | 0.7 ft | 0.91 |
| Ocean Beach | SF029 | 1.08 | 1.2 ft | 0.95 |
| Mavericks | SM305 | 1.05 | 0.9 ft | 0.94 |
| Stinson | MA123 | 1.10 | 0.5 ft | 0.93 |
| Princeton Jetty | SM297 (1.1 km away: MOP has no point at the jetty) | 1.05 | 0.5 ft | 0.93 |
| Steamer Lane | SC149 | 0.91 | 0.5 ft | 0.94 |
| Pleasure Point | SC117 | 0.95 | 0.4 ft | 0.93 |

Two independent models agreeing within ~10% is good evidence the 10 m spot grids are right, but
MOP is a model, not a measurement. MOP's shore directions also match ours within 6° except Mavericks
(221° vs 238°), where the coast bends sharply.

**Surf height** (shown on the pages) is the face height of breaking waves: from the significant
breaker height (Komar & Gaudiano 1975; average of the biggest third) up to 1.25x that for the sets
(`SURF_RANGE` in predict.py). It's computed from a second table traced in the breaking zone at the
marked spot (~4 m deep, `W_break`; `build_tables.py --break-only`), not the ~10 m model point: swell
keeps bending over the last few hundred metres, a lot in sheltered corners. At Princeton Jetty on
2026-11-09 the wave height at 4.5 m was 4.6 ft vs 6.9 ft at the 8.6 m point (where CDIP's model
agreed at 6.8 ft); surf went from 9.5-11.8 to 6.1-7.6 ft against an observed ~4-5 ft. The wave height feeding it is checked (above); the breaking step isn't yet,
and needs observations at the breaks.

## Known limitations
- Ray theory ignores diffraction, so it under-predicts energy leaking into sheltered corners.
- NOAA's depth data is survey-grade only deeper than ~10 m; inside that (where waves break) it's smooth fill,
  even in the 3 m CUDEM tiles. So the lineup view gets the shape of a point or reef but not individual sections.
  Steamer Lane and Pleasure Point come out as rights, as they are. Mavericks doesn't: the reef that makes its
  famous right isn't resolved, and its spots.csv marker sits on Pillar Point rather than on the peak.
  The 10 m grids are smoothed to ~30 m because finer features don't bend swell-length waves.
- No wind, tide, currents or sandbars. Surf heights use a generic breaking formula that is **not yet calibrated**
  against observed surf (the wave heights feeding it are; see check_mop.py).
- The forecast is swell only (no wind or tide yet). WaveWatch III's 10° direction bins are coarser than a
  buoy's, and NOAA keeps only ~2 days of runs online, so scoring the forecast relies on our own log (`forecast_log.py`).
