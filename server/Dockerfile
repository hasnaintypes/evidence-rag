FROM python:3.11-slim

WORKDIR /app

# Build context is the repo root (see docker-compose.yml) so server/ and
# docs/ keep the same relative layout as local dev - src/config.py locates
# docs/fixtures/sample_docs by walking up from its own file path, and that
# math only lines up if the two folders stay siblings inside the image too.
COPY server/requirements.txt server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt

COPY server/ server/
COPY docs/ docs/

# Runs as a dedicated non-root user rather than the image default (root) -
# a container breakout or a vulnerability in a dependency shouldn't hand
# an attacker root inside the container. server/data/ (local-mode SQLite
# DB) and docs/fixtures/sample_docs/ (local-mode file storage, including
# per-user uploads via POST /upload - see src/storage/files.py) are the
# only paths this process writes to at runtime, so only those need to be
# writable; everything else can stay read-only for appuser. The container
# still starts as root - entrypoint.sh fixes ownership of these paths
# (needed every start, not just at build time: docker-compose.yml
# bind-mounts ./server/data over /app/server/data, and a bind mount's
# ownership comes from the host side, not this image) before dropping to
# appuser to run the actual process.
RUN groupadd --system appuser && useradd --system --gid appuser --create-home --home-dir /home/appuser appuser \
    && mkdir -p /app/server/data \
    && chown -R appuser:appuser /app/server/data /app/docs/fixtures/sample_docs /home/appuser

COPY server/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENV HOME=/home/appuser
ENTRYPOINT ["/app/entrypoint.sh"]

WORKDIR /app/server
EXPOSE 8000

CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]
