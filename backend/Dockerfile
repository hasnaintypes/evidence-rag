FROM python:3.11-slim

WORKDIR /app

# Build context is the repo root (see docker-compose.yml) so backend/ and
# docs/ keep the same relative layout as local dev - src/config.py locates
# docs/sample_docs by walking up from its own file path, and that math
# only lines up if the two folders stay siblings inside the image too.
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
COPY docs/ docs/

WORKDIR /app/backend
EXPOSE 8000

CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]
