FROM golang:1.26.3-bookworm@sha256:386d475a660466863d9f8c766fec64d7fdad3edac2c6a05020c09534d71edb4b AS grafana-mcp-builder
RUN CGO_ENABLED=0 go install github.com/grafana/mcp-grafana/cmd/mcp-grafana@v1.0.0

FROM python:3.12-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    DAILIES_STATIC_INDEX=/app/static/index.html \
    DAILIES_FIXTURE_PATH=/app/fixtures/telemetry_v1.json
WORKDIR /app
COPY --from=grafana-mcp-builder /go/bin/mcp-grafana /usr/local/bin/mcp-grafana
COPY --from=grafana-mcp-builder /go/pkg/mod/github.com/grafana/mcp-grafana@v1.0.0/LICENSE /usr/share/licenses/mcp-grafana/LICENSE
COPY pyproject.toml requirements.lock README.md LICENSE THIRD_PARTY_NOTICES.md ./
COPY src ./src
RUN pip install --no-cache-dir --constraint requirements.lock .
COPY static ./static
COPY scripts ./scripts
COPY fixtures ./fixtures
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser
CMD ["sh", "-c", "uvicorn dailies_guardian.service:app --host 0.0.0.0 --port ${PORT}"]
