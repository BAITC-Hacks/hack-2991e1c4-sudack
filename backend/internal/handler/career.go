package handler

import (
	"encoding/json"
	"io"
	"net/http"

	"github.com/BAITC-Hacks/hack-2991e1c4-sudack/internal/domain/errs"
	"github.com/labstack/echo/v4"
)

func requireEmployeeAccess(c echo.Context, employeeID string, allowHR bool) error {
	role, _ := c.Get("role").(string)
	subject, _ := c.Get("subject").(string)
	if subject == employeeID && role == "employee" {
		return nil
	}
	if allowHR && role == "hr" {
		return nil
	}
	return errs.NewError(http.StatusForbidden, "FORBIDDEN", "access denied")
}

func requireHR(c echo.Context) error {
	if c.Get("role") == "hr" {
		return nil
	}
	return errs.NewError(http.StatusForbidden, "FORBIDDEN", "HR access required")
}

// Profile godoc
// @Summary Профиль и прогресс сотрудника
// @Tags employees
// @Produce json
// @Security BearerAuth
// @Success 200 {object} map[string]interface{}
// @Router /api/v1/employees/{employee_id} [get]
func (h *Handler) Profile(c echo.Context) error {
	id := c.Param("employee_id")
	if err := requireEmployeeAccess(c, id, true); err != nil {
		return err
	}
	profile, err := h.service.Profile(c.Request().Context(), id, c.QueryParam("lang"))
	if err != nil {
		return err
	}
	return c.JSON(http.StatusOK, profile)
}

// Recommendations godoc
// @Summary Рекомендации AI и объяснения
// @Tags employees
// @Produce json
// @Security BearerAuth
// @Success 200 {object} map[string]interface{}
// @Router /api/v1/employees/{employee_id}/recommendations [get]
func (h *Handler) Recommendations(c echo.Context) error {
	id := c.Param("employee_id")
	if err := requireEmployeeAccess(c, id, true); err != nil {
		return err
	}
	result, err := h.service.Recommend(c.Request().Context(), id, c.QueryParam("lang"))
	if err != nil {
		return err
	}
	return c.Blob(http.StatusOK, echo.MIMEApplicationJSON, result)
}

// Roadmap godoc
// @Summary План перехода на следующий грейд
// @Tags employees
// @Produce json
// @Security BearerAuth
// @Success 200 {object} map[string]interface{}
// @Router /api/v1/employees/{employee_id}/roadmap [get]
func (h *Handler) Roadmap(c echo.Context) error {
	id := c.Param("employee_id")
	if err := requireEmployeeAccess(c, id, true); err != nil {
		return err
	}
	result, err := h.service.Simulate(c.Request().Context(), id, c.QueryParam("lang"))
	if err != nil {
		return err
	}
	return c.Blob(http.StatusOK, echo.MIMEApplicationJSON, result)
}

// Preview godoc
// @Summary Прогноз роста после активности
// @Tags employees
// @Produce json
// @Security BearerAuth
// @Success 200 {object} map[string]interface{}
// @Router /api/v1/employees/{employee_id}/events/{event_id}/preview [post]
func (h *Handler) Preview(c echo.Context) error {
	id := c.Param("employee_id")
	if err := requireEmployeeAccess(c, id, true); err != nil {
		return err
	}
	result, err := h.service.Preview(c.Request().Context(), id, c.Param("event_id"))
	if err != nil {
		return err
	}
	return c.JSON(http.StatusOK, result)
}

// Completion godoc
// @Summary Отметить активность завершённой
// @Tags employees
// @Produce json
// @Security BearerAuth
// @Param Idempotency-Key header string true "Unique completion request key"
// @Success 200 {object} map[string]interface{}
// @Router /api/v1/employees/{employee_id}/events/{event_id}/completions [post]
func (h *Handler) Completion(c echo.Context) error {
	id := c.Param("employee_id")
	if err := requireEmployeeAccess(c, id, false); err != nil {
		return err
	}
	result, err := h.service.Complete(c.Request().Context(), id, c.Param("event_id"), c.Request().Header.Get("Idempotency-Key"))
	if err != nil {
		return err
	}
	return c.JSON(http.StatusOK, result)
}

// HROverview godoc
// @Summary HR-срез навыков, участия и риска выпадения
// @Tags hr
// @Produce json
// @Security BearerAuth
// @Success 200 {object} map[string]interface{}
// @Router /api/v1/hr/overview [get]
func (h *Handler) HROverview(c echo.Context) error {
	if err := requireHR(c); err != nil {
		return err
	}
	result, err := h.service.HROverview(c.Request().Context())
	if err != nil {
		return err
	}
	return c.JSON(http.StatusOK, result)
}

// HREmployees godoc
// @Summary Список ID сотрудников для HR
// @Tags hr
// @Produce json
// @Security BearerAuth
// @Success 200 {object} map[string]interface{}
// @Router /api/v1/hr/employees [get]
func (h *Handler) HREmployees(c echo.Context) error {
	if err := requireHR(c); err != nil {
		return err
	}
	ids, err := h.service.EmployeeIDs(c.Request().Context())
	if err != nil {
		return err
	}
	return c.JSON(http.StatusOK, map[string]any{"employees": ids})
}

// EventImpact godoc
// @Summary Оценить проект HR-активности до публикации
// @Tags hr
// @Accept json
// @Produce json
// @Security BearerAuth
// @Success 200 {object} map[string]interface{}
// @Router /api/v1/hr/events/impact [post]
func (h *Handler) EventImpact(c echo.Context) error {
	if err := requireHR(c); err != nil {
		return err
	}
	data, err := io.ReadAll(io.LimitReader(c.Request().Body, 1<<20))
	if err != nil || !json.Valid(data) {
		return errs.ErrInvalidParameter
	}
	result, err := h.service.EventImpact(c.Request().Context(), json.RawMessage(data))
	if err != nil {
		return err
	}
	return c.Blob(http.StatusOK, echo.MIMEApplicationJSON, result)
}
