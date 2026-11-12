# Common tasks. `make help` lists them.
PY      ?= python3
IMAGE   ?= surfmodel
PORT    ?= 8000
DATA    ?= $(CURDIR)/out/data
SNAP    ?=
ENV     ?= prod
JOB     ?= all
CHECKDIR ?= $(CURDIR)/out/snapshot-check

.PHONY: emulators emulator-job cloud-setup deploy cloud-job help install publish hourly forecast nightly serve dev pages check snapshot \
        docker-build docker-hourly docker-forecast docker-nightly docker-all

help:                ## list the tasks
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed 's/:[^#]*## /\t/' | expand -t 18

install:             ## install the Python packages (plus the plotting extras)
	$(PY) -m pip install -r requirements-dev.txt

publish:             ## publish everything for every spot into out/data
	$(PY) jobs.py all
hourly:              ## the hourly job: current swells, surf height, lineup, conditions
	$(PY) jobs.py hourly
forecast:            ## the 6-hourly job: 7-day forecast
	$(PY) jobs.py forecast
nightly:             ## the nightly job: maps and spot index
	$(PY) jobs.py nightly

serve:               ## run the website on http://localhost:8000 (reads out/data)
	$(PY) serve.py $(PORT)
dev: publish serve   ## publish fresh data, then run the website

pages:               ## the single-file spot pages, out/ribbons_*.html
	$(PY) ribbons.py

snapshot:            ## record the regression baseline: make snapshot SNAP=<dir>
	@test -n "$(SNAP)" || (echo "set SNAP=<dir>"; exit 1)
	$(PY) tests/snapshot.py save $(SNAP)
check:               ## compare with the baseline, directly and via published files: make check SNAP=<dir>
	@test -n "$(SNAP)" || (echo "set SNAP=<dir> (recorded with make snapshot)"; exit 1)
	$(PY) tests/snapshot.py check $(SNAP)
	$(PY) tests/snapshot.py check-published $(SNAP) $(CHECKDIR)

emulators:           ## the whole system locally (Firebase emulators in Docker): site :5050, emulator UI :4000
	$(PY) deploy/build_web.py emulator
	mkdir -p .emulator-data build
	docker compose up --build emulators
emulator-job:        ## run a job into the emulators (while `make emulators` runs): make emulator-job JOB=all
	docker compose run --rm --build jobs $(JOB)

cloud-setup:         ## one-time setup of the cloud project: make cloud-setup (ENV=prod by default)
	deploy/setup.sh $(ENV)
deploy:              ## deploy jobs, schedules and the site: make deploy (ENV=prod by default)
	deploy/deploy.sh $(ENV)
cloud-job:           ## run a job in the cloud now and wait for it: make cloud-job JOB=all
	. deploy/$(ENV).env && gcloud run jobs execute surf-nightly --project="$$PROJECT" --region="$$REGION" --args=$(JOB) --wait

docker-build:        ## build the jobs image
	docker build -t $(IMAGE) .
docker-hourly: docker-build    ## run a job in the image, writing to out/data (also docker-forecast, -nightly, -all)
	mkdir -p $(DATA) && docker run --rm -v "$(DATA):/data" $(IMAGE) hourly
docker-forecast: docker-build
	mkdir -p $(DATA) && docker run --rm -v "$(DATA):/data" $(IMAGE) forecast
docker-nightly: docker-build
	mkdir -p $(DATA) && docker run --rm -v "$(DATA):/data" $(IMAGE) nightly
docker-all: docker-build
	mkdir -p $(DATA) && docker run --rm -v "$(DATA):/data" $(IMAGE) all
