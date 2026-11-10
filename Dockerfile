# The model and its scheduled jobs, as one image. The same image runs locally (make docker-hourly)
# and as Cloud Run Jobs: the job name is the argument, the output location is SURF_STORE.
#
#   docker build -t surfmodel .
#   docker run --rm -v "$PWD/out/data:/data" surfmodel hourly
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MPLBACKEND=Agg \
    MPLCONFIGDIR=/tmp/matplotlib \
    SURF_STORE=local:/data

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

# Code, spots.csv and the model's data (depth grids and transfer tables, ~20 MB).
COPY . .

# Run as a normal user; it only writes its forecast download cache and the output folder.
RUN useradd --create-home surf \
 && mkdir -p data/forecast /data \
 && chown surf data/forecast /data
USER surf

ENTRYPOINT ["python", "jobs.py"]
CMD ["hourly"]
