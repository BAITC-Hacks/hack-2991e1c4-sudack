package main

import (
	"context"
	"flag"
	"log"
	"os"

	"github.com/BAITC-Hacks/hack-2991e1c4-sudack/internal/bootstrap"
)

func main() {
	dbPath := flag.String("db", envOr("DB_PATH", ".local/db/test.db"), "SQLite database path")
	dataDir := flag.String("data", envOr("DATA_DIR", "../sudack-ai/docs/data"), "dataset directory")
	appendMode := flag.Bool("append", false, "append new employees and history to an existing database")
	flag.Parse()

	if *appendMode {
		added, err := bootstrap.Append(context.Background(), *dbPath, *dataDir)
		if err != nil {
			log.Fatalf("bootstrap.Append: %v", err)
		}
		log.Printf("added %d employees and imported new history rows into %s", added, *dbPath)
		return
	}

	created, err := bootstrap.Initialize(context.Background(), *dbPath, *dataDir)
	if err != nil {
		log.Fatalf("bootstrap.Initialize: %v", err)
	}
	if created {
		log.Printf("database initialized: %s", *dbPath)
		return
	}
	log.Printf("database already exists: %s", *dbPath)
}

func envOr(key, fallback string) string {
	value := os.Getenv(key)
	if value != "" {
		return value
	}
	return fallback
}
