# db/Dockerfile  – builds the image that loads & populates Memgraph
FROM python:3.11-slim

WORKDIR /app

# Ensure /app is on Python import path so `import db` resolves whether
# the package was copied into /app/db or mounted at runtime.
ENV PYTHONPATH=/app

# ------------------------------------------------------------------
# 1. Build-time deps – gcc, g++, make, cmake … needed for pymgclient
# ------------------------------------------------------------------
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        libpq-dev \
        libssl-dev; \
    pip install --upgrade pip

# ------------------------------------------------------------------
# 2. Install Python deps first (cached layer)
# ------------------------------------------------------------------
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

# ------------------------------------------------------------------
# 3. Copy only the db package into the image
# ------------------------------------------------------------------
COPY db/ db/
COPY db/memgraph_domain/populate.py /app/populate.py

# ------------------------------------------------------------------
# 4. (Optional) strip tool-chain to keep runtime image small
# ------------------------------------------------------------------
RUN set -eux; \
    apt-get purge -y --auto-remove \
        build-essential \
        cmake \
        libpq-dev \
        libssl-dev; \
    rm -rf /var/lib/apt/lists/*

CMD ["python", "-m", "db.populate"]
