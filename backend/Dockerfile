FROM golang:1.26.1-bookworm AS builder

WORKDIR /src
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev && rm -rf /var/lib/apt/lists/*
COPY go.mod go.sum ./
RUN go mod download
COPY cmd ./cmd
COPY internal ./internal
RUN CGO_ENABLED=1 go build -trimpath -ldflags="-s -w" -o /out/careerquest ./cmd

FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends sqlite3 ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app/backend
COPY --from=builder /out/careerquest ./careerquest
COPY internal/migrations/1_init.sql ./internal/migrations/1_init.sql
COPY docker/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh && mkdir -p /app/.local/db && chown -R 10001:10001 /app
USER 10001:10001
ENV PORT=8080
EXPOSE 8080
VOLUME ["/app/.local/db"]
ENTRYPOINT ["/app/entrypoint.sh"]
