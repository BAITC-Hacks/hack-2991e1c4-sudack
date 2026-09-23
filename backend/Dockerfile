# Go API. CGO is required by github.com/mattn/go-sqlite3.
FROM golang:1.26-bookworm AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=1 go build -o /out/server ./cmd

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*
# main.go opens ../.local/db/test.db relative to the working directory.
WORKDIR /srv/app
RUN mkdir -p /srv/.local/db
COPY --from=build /out/server /srv/app/server
ENV PORT=8080
EXPOSE 8080
CMD ["/srv/app/server"]
