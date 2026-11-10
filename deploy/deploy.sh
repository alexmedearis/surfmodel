#!/usr/bin/env bash
# Deploy the current code to a cloud environment: the jobs image, the three Cloud Run Jobs and
# their schedules, the website and the Storage rules.
#
#   deploy/deploy.sh staging
#   deploy/deploy.sh prod            (only from a clean, committed tree)
#
# Run deploy/setup.sh <env> once first. After the first deploy, fill the bucket right away
# instead of waiting for the schedules:  make cloud-job ENV=<env> JOB=all
set -euo pipefail
cd "$(dirname "$0")/.."
ENV_NAME=${1:?usage: deploy/deploy.sh staging|prod}
# shellcheck disable=SC1090
source "deploy/$ENV_NAME.env"
case "$PROJECT" in CHANGE-ME*|demo-*) echo "set PROJECT and BUCKET in deploy/$ENV_NAME.env first"; exit 1;; esac

DIRTY=""
git diff --quiet HEAD -- || DIRTY="-dirty"
if [ "$ENV_NAME" = prod ] && [ -n "$DIRTY" ]; then
  echo "commit your changes before deploying to prod"; exit 1
fi
TAG="$(git rev-parse --short HEAD)$DIRTY"
IMAGE="$REGION-docker.pkg.dev/$PROJECT/surf/surfmodel:$TAG"
G="gcloud --project=$PROJECT --quiet"
JOBS_SA="surf-jobs@$PROJECT.iam.gserviceaccount.com"
SCHED_SA="surf-scheduler@$PROJECT.iam.gserviceaccount.com"

schedule() {                      # UTC cron for each job
  case "$1" in
    hourly)   echo "10 * * * *" ;;           # buoys report every 30-60 min
    forecast) echo "40 5,11,17,23 * * *" ;;  # ~5.5 h after each WaveWatch III run (00/06/12/18 UTC)
    nightly)  echo "20 10 * * *" ;;          # 2-3 am in California
  esac
}

echo "== image $IMAGE"
gcloud auth configure-docker "$REGION-docker.pkg.dev" --quiet >/dev/null
docker buildx build --platform linux/amd64 -t "$IMAGE" --push .   # Cloud Run runs Intel/AMD machines

for JOB in hourly forecast nightly; do
  echo "== job surf-$JOB"
  $G run jobs deploy "surf-$JOB" --region="$REGION" --image="$IMAGE" --args="$JOB" \
     --service-account="$JOBS_SA" --set-env-vars="SURF_STORE=gs://$BUCKET" \
     --cpu=2 --memory=2Gi --task-timeout=30m --max-retries=1
  URI="https://run.googleapis.com/v2/projects/$PROJECT/locations/$REGION/jobs/surf-$JOB:run"
  VERB=create
  $G scheduler jobs describe "surf-$JOB" --location="$REGION" >/dev/null 2>&1 && VERB=update
  $G scheduler jobs "$VERB" http "surf-$JOB" --location="$REGION" --schedule="$(schedule "$JOB")" \
     --time-zone=UTC --uri="$URI" --http-method=POST --oauth-service-account-email="$SCHED_SA"
done

echo "== website and Storage rules"
python3 deploy/build_web.py "$ENV_NAME"
firebase deploy --project "$PROJECT" --only hosting,storage --non-interactive

echo "deployed $TAG to $ENV_NAME: https://$PROJECT.web.app"
