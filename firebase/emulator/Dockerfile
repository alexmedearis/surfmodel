# The Firebase emulators (Storage, Hosting, Auth, Firestore + their web UI) in a container,
# so they don't need Java or Node installed on the laptop. Used by docker-compose.yml.
FROM node:22-trixie-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends openjdk-21-jre-headless \
 && rm -rf /var/lib/apt/lists/* \
 && npm install -g firebase-tools@15.35.0
WORKDIR /work
EXPOSE 4000 4400 4500 5050 8080 9099 9199
