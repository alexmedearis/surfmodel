#!/usr/bin/env bash
# One-time setup of a cloud environment (staging or prod). Safe to run again.
#
#   deploy/setup.sh staging
#
# Before this, in the Firebase console (console.firebase.google.com):
#   1. create the project and put it on the Blaze (pay as you go) plan
#   2. Storage -> Get started (this creates the bucket the data goes in)
#   3. Hosting -> Get started
# then put the project id and bucket name in deploy/<env>.env.
#
# What it sets up: the APIs it needs, a place for the Docker image, and two service accounts with
# only the access they need: surf-jobs (runs the model; may write the data bucket) and
# surf-scheduler (may start the jobs on their schedule).
set -euo pipefail
cd "$(dirname "$0")/.."
ENV_NAME=${1:?usage: deploy/setup.sh staging|prod}
# shellcheck disable=SC1090
source "deploy/$ENV_NAME.env"
case "$PROJECT" in CHANGE-ME*|demo-*) echo "set PROJECT and BUCKET in deploy/$ENV_NAME.env first"; exit 1;; esac

G="gcloud --project=$PROJECT --quiet"
JOBS_SA="surf-jobs@$PROJECT.iam.gserviceaccount.com"
SCHED_SA="surf-scheduler@$PROJECT.iam.gserviceaccount.com"

echo "== APIs"
$G services enable run.googleapis.com cloudscheduler.googleapis.com artifactregistry.googleapis.com

echo "== image registry ($REGION)"
$G artifacts repositories describe surf --location="$REGION" >/dev/null 2>&1 ||
  $G artifacts repositories create surf --repository-format=docker --location="$REGION" \
     --description="Surf model images"

echo "== service accounts"
$G iam service-accounts describe "$JOBS_SA" >/dev/null 2>&1 ||
  $G iam service-accounts create surf-jobs --display-name="Surf model jobs"
$G iam service-accounts describe "$SCHED_SA" >/dev/null 2>&1 ||
  $G iam service-accounts create surf-scheduler --display-name="Surf model job scheduler"

echo "== access"
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" --project="$PROJECT" --quiet \
  --member="serviceAccount:$JOBS_SA" --role=roles/storage.objectAdmin >/dev/null
$G projects add-iam-policy-binding "$PROJECT" --condition=None \
  --member="serviceAccount:$SCHED_SA" --role=roles/run.invoker >/dev/null

echo "done: $ENV_NAME ($PROJECT) is ready for deploy/deploy.sh $ENV_NAME"
