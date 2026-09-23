package main

import (
	"database/sql"
	"log"

	"github.com/BAITC-Hacks/hack-2991e1c4-sudack/internal/config"
	"github.com/BAITC-Hacks/hack-2991e1c4-sudack/internal/handler"
	"github.com/BAITC-Hacks/hack-2991e1c4-sudack/internal/repository/sqlite"
	"github.com/BAITC-Hacks/hack-2991e1c4-sudack/internal/server"
	"github.com/BAITC-Hacks/hack-2991e1c4-sudack/internal/service"

	_ "github.com/mattn/go-sqlite3"
)

func main() {
	cfg, err := config.NewConfig()
	if err != nil {
		log.Fatalf("config.NewConfig: %v", err)
	}

	db, err := sql.Open("sqlite3", cfg.DBPath)
	if err != nil {
		log.Fatalf("sql.Open: %v", err)
	}
	defer db.Close()

	sqliteRepository, err := sqlite.NewRepository(db)
	if err != nil {
		log.Fatalf("sqlite.NewRepository: %v", err)
	}

	service, err := service.NewService(sqliteRepository)
	if err != nil {
		log.Fatalf("service.NewService: %v", err)
	}

	handler, err := handler.NewHandler(service)
	if err != nil {
		log.Fatalf("handler.NewHandler: %v", err)
	}

	srv, err := server.NewServer(handler)
	if err != nil {
		log.Fatalf("server.NewServer: %v", err)
	}

	if err = srv.Start(cfg.Port); err != nil {
		log.Fatalf("srv.Start: %v", err)
	}
}
