FROM golang:1.26.1-bookworm AS builder

WORKDIR /src
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev && rm -rf /var/lib/apt/lists/*
COPY go.mod go.sum ./
RUN go mod download
COPY cmd ./cmd
COPY internal ./internal
RUN CGO_ENABLED=1 go build -trimpath -ldflags="-s -w" -o /out/careerquest ./cmd
RUN CGO_ENABLED=1 go build -trimpath -ldflags="-s -w" -o /out/careerquest-migrate ./cmd/migrate
RUN CGO_ENABLED=1 go build -trimpath -ldflags="-s -w" -o /out/careerquest-token ./cmd/token

FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app/backend
COPY --from=builder /out/careerquest ./careerquest
COPY --from=builder /out/careerquest-migrate ./careerquest-migrate
COPY --from=builder /out/careerquest-token ./careerquest-token
COPY docker/entrypoint.sh /app/entrypoint.sh
# Normalize line endings: a CRLF checkout on Windows breaks the shebang.
RUN sed -i 's/$//' /app/entrypoint.sh && chmod +x /app/entrypoint.sh && mkdir -p /app/.local/db && chown -R 10001:10001 /app
USER 10001:10001
ENV PORT=8080 DB_PATH=/app/.local/db/test.db DATA_DIR=/app/data AI_URL=http://ai:8001
EXPOSE 8080
VOLUME ["/app/.local/db"]
ENTRYPOINT ["/app/entrypoint.sh"]
