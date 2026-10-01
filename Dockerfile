# AIOS-0X Command Center — reproducible multi-stage build
# Stage 1: build the React frontend from the frontend project root.
FROM node:22-slim AS frontend-builder
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# frontend/vite.config.ts emits ../ui/dist, i.e. /build/ui/dist.
RUN npm run build

# Stage 2: Python runtime + compiled frontend
FROM python:3.12-slim AS runtime
WORKDIR /app

# pyproject.toml is the ONE dependency model. The source tree is copied before
# installing because the project is installed from itself, and the extras select
# the server-grade backends this image ships with: the PostgreSQL financial
# store and the NATS JetStream event backbone.
#
# CONSTITUTION.md ships because core/constitution.py verifies it against a
# SHA-256 pin on every boot. An image that cannot read the file it verifies
# cannot enforce the pin.
COPY pyproject.toml CONSTITUTION.md /app/
#
# One COPY per package, each with its own destination. `COPY a b c /app/`
# flattens: Docker treats the destination as a single directory and merges
# every source's *contents* into it, so core/, kernel/ and scripts/ all landed
# as /app/*.py and `import core` could never resolve. The symptom was a
# ModuleNotFoundError after a successful pip install, which reads like a
# packaging problem and is not one -- the wheel was empty because the source
# layout it was pointed at did not exist.
COPY aios/ /app/aios/
COPY api/ /app/api/
COPY communities/ /app/communities/
COPY core/ /app/core/
COPY evaluation/ /app/evaluation/
COPY kernel/ /app/kernel/
COPY research/ /app/research/
COPY schemas/ /app/schemas/
COPY scripts/ /app/scripts/
COPY simulation/ /app/simulation/
RUN pip install --no-cache-dir ".[postgres,nats]" && \
    python -c "import core.pg_financial_store, core.jetstream_bus, core.migrations; print('backends importable')"

# Immutable reference data.
COPY data/golden /app/data/golden
COPY --from=frontend-builder /build/ui/dist /app/ui/dist

# The service writes only to /app/data (normally a mounted volume) and /tmp.
RUN mkdir -p /app/data /tmp && \
    groupadd -r aios && \
    useradd -r -g aios -d /app aios && \
    chown -R aios:aios /app /tmp

USER aios
EXPOSE 8787
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/api/v1/health', timeout=3)"
# Bind all container interfaces; Compose/reverse proxy controls exposure.
CMD ["python", "-u", "-W", "ignore", "scripts/serve_command_center.py", "--host", "0.0.0.0", "--port", "8787"]
