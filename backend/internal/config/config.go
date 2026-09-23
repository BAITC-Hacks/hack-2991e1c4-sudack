package config

import (
	"fmt"

	"github.com/kelseyhightower/envconfig"
)

type Config struct {
	Port       int    `envconfig:"PORT" default:"8080"`
	DBPath     string `envconfig:"DB_PATH" default:".local/db/test.db"`
	AIURL      string `envconfig:"AI_URL" default:"http://localhost:8001"`
	AuthSecret string `envconfig:"AUTH_SECRET" default:"careerquest-local-demo-secret"`
}

func NewConfig() (*Config, error) {
	var cfg Config
	if err := envconfig.Process("", &cfg); err != nil {
		return nil, fmt.Errorf("envconfig.Process: %w", err)
	}
	return &cfg, nil
}
