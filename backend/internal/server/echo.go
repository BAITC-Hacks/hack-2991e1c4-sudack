package server

import (
	"context"
	"fmt"

	"github.com/BAITC-Hacks/hack-2991e1c4-sudack/internal/handler"
	"github.com/labstack/echo/v4"
)

type Server struct {
	echo *echo.Echo
}

func NewServer(h *handler.Handler) (*Server, error) {
	e := echo.New()
	e.HTTPErrorHandler = newEchoErrorHandler()

	return &Server{
		echo: e,
	}, nil
}

func (s *Server) Start(port int) error {
	return s.echo.Start(fmt.Sprintf(":%d", port))
}

func (s *Server) Shutdown(ctx context.Context) error {
	return s.echo.Shutdown(ctx)
}
