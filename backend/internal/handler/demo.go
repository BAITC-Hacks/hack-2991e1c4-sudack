package handler

import (
	"net/http"
	"sort"

	"github.com/labstack/echo/v4"
)

// DemoEmployees godoc
// @Summary Список сотрудников для экрана входа в демо-режиме
// @Description Публичен только при DEMO_AUTH=true. Данные синтетические; в реальном контуре список выдаётся после аутентификации.
// @Tags auth
// @Produce json
// @Success 200 {object} map[string]interface{}
// @Router /api/v1/auth/demo-employees [get]
func (h *Handler) DemoEmployees(c echo.Context) error {
	summaries, err := h.service.EmployeeSummaries(c.Request().Context())
	if err != nil {
		return err
	}
	items := make([]map[string]any, 0, len(summaries))
	for _, item := range summaries {
		items = append(items, map[string]any{
			"employee_id": item.ID, "full_name": item.FullName, "department": item.Department,
			"role": item.Role, "grade": item.Grade,
		})
	}
	sort.Slice(items, func(i, j int) bool { return items[i]["employee_id"].(string) < items[j]["employee_id"].(string) })
	return c.JSON(http.StatusOK, map[string]any{"employees": items, "count": len(items)})
}
