#!/bin/sh
# Start the emulators, loading the data saved by the previous run if there is any
# (firebase refuses --import of a folder with nothing saved in it yet). The export is written
# to a temp folder and then moved into place, so the temp folder has to be on the same mount.
STATE=/work/state
DATA=$STATE/data
mkdir -p "$STATE/tmp"
export TMPDIR="$STATE/tmp"
IMPORT=""
if [ -f "$DATA/firebase-export-metadata.json" ]; then
  IMPORT="--import=$DATA"
fi
exec firebase emulators:start --project demo-surf --export-on-exit="$DATA" $IMPORT
