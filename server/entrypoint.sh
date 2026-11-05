#!/bin/sh
# Runs as root (the image's default user) so it can fix ownership of paths
# whose actual on-disk owner isn't known until the container actually
# starts, then drops to appuser for the real process:
#
# - server/data: when STORAGE_MODE=local and docker-compose.yml bind-mounts
#   ./server/data over it, the mount's ownership comes from the host side
#   (root, since Docker auto-creates missing bind-mount sources as root),
#   not from this image's build-time chown - so it has to be re-applied
#   every container start, not just once in the Dockerfile.
# - appuser's $HOME: --no-create-home left it absent. Reranking no longer
#   needs this (src/retrieval/reranker.py is a Gemini call now, not a
#   locally-cached model - see #20), but other libraries can still default
#   to writing cache files under $HOME, so it stays writable defensively.
set -e

mkdir -p /app/server/data "$HOME"
chown -R appuser:appuser /app/server/data /app/docs/fixtures/sample_docs "$HOME"

exec su -s /bin/sh appuser -c 'exec "$0" "$@"' -- "$@"
