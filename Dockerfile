# AIOS-0X Command Center — multi-stage build
FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim
RUN groupadd -r aios && useradd -r -g aios -d /app aios
WORKDIR /app
COPY --from=builder /install /usr/local
COPY --chown=aios:aios . .
RUN mkdir -p /app/data && chown aios:aios /app/data
USER aios
EXPOSE 8787
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/api/v1/health', timeout=3)"
CMD ["python", "-u", "-W", "ignore", "scripts/serve_command_center.py", "--port", "8787"]
