package handler

import (
	"net/http"

	_ "github.com/BAITC-Hacks/hack-2991e1c4-sudack/internal/domain/errs"
	"github.com/labstack/echo/v4"
)

// Health godoc
// @Summary Проверить работоспособность сервиса
// @Description Выполняет SELECT 1 в SQLite. Эндпоинт публичный и не проверяет Python-сервис.
// @Tags health
// @Produce json
// @Success 200 {object} HealthResponse
// @Failure 503 {object} errs.Error
// @Router /healthz [get]
func (h *Handler) Health(c echo.Context) error {
	if err := h.service.Health(c.Request().Context()); err != nil {
		return err
	}

	return c.JSON(http.StatusOK, HealthResponse{
		Status:   "ok",
		Database: "ok",
	})
}
