FROM python:3.12-slim

LABEL org.opencontainers.image.title="teslamate-supercharger-costs" \
      org.opencontainers.image.description="Imports real Supercharger costs from Tesla API into TeslaMate" \
      org.opencontainers.image.source="https://github.com/slallemand/teslamate-supercharger-costs" \
      org.opencontainers.image.licenses="MIT"

WORKDIR /app

# Install dependencies in a separate layer for better caching
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY importer.py .
COPY scripts/ ./scripts/

# Backward-compatible path (older docs/images used /app/export_ha_statistics.py).
RUN ln -sf scripts/export_ha_statistics.py export_ha_statistics.py

# Persistent volumes for token cache and logs
VOLUME ["/data", "/logs"]

ENTRYPOINT ["python", "importer.py"]
