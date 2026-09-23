package server

import (
	"context"
	"fmt"
	"net/http"
	"os"
	"strings"

	"github.com/BAITC-Hacks/hack-2991e1c4-sudack/internal/handler"
	"github.com/labstack/echo/v4"
	"github.com/labstack/echo/v4/middleware"
)

type Server struct {
	echo *echo.Echo
}

func NewServer(h *handler.Handler, authSecret string) (*Server, error) {
	e := echo.New()
	corsOrigins := os.Getenv("CORS_ORIGINS")
	if corsOrigins == "" {
		corsOrigins = "http://localhost:5173,http://localhost:3000"
	}
	e.Use(middleware.CORSWithConfig(middleware.CORSConfig{
		AllowOrigins: strings.Split(corsOrigins, ","),
		AllowHeaders: []string{echo.HeaderAuthorization, echo.HeaderContentType, "Idempotency-Key"},
		AllowMethods: []string{http.MethodGet, http.MethodPost, http.MethodOptions},
	}))
	e.HTTPErrorHandler = newEchoErrorHandler()
	e.GET("/healthz", h.Health)

	api := e.Group("/api/v1", authenticate(authSecret))
	api.GET("/employees/:employee_id", h.Profile)
	api.GET("/employees/:employee_id/recommendations", h.Recommendations)
	api.GET("/employees/:employee_id/roadmap", h.Roadmap)
	api.POST("/employees/:employee_id/events/:event_id/preview", h.Preview)
	api.POST("/employees/:employee_id/events/:event_id/completions", h.Completion)
	api.GET("/hr/overview", h.HROverview)
	api.GET("/hr/employees", h.HREmployees)
	api.POST("/hr/events/impact", h.EventImpact)

	return &Server{echo: e}, nil
}

func (s *Server) Start(port int) error {
	return s.echo.Start(fmt.Sprintf(":%d", port))
}

func (s *Server) Shutdown(ctx context.Context) error {
	return s.echo.Shutdown(ctx)
}
