package handler

import (
	"io"
	"mime/multipart"
	"net/http"

	"github.com/BAITC-Hacks/hack-2991e1c4-sudack/internal/domain/errs"
	"github.com/labstack/echo/v4"
)

const importFileLimit = 32 << 20

// Imports godoc
// @Summary Загрузить дополнительные профили и историю в формате стартового кита
// @Description multipart/form-data с файлами employees (employees.json) и/или history (activity_history.csv). Существующие сотрудники и записи не меняются.
// @Tags hr
// @Accept multipart/form-data
// @Produce json
// @Security BearerAuth
// @Success 200 {object} map[string]interface{}
// @Failure 422 {object} errs.Error
// @Router /api/v1/imports [post]
func (h *Handler) Imports(c echo.Context) error {
	if err := requireHR(c); err != nil {
		return err
	}
	c.Request().Body = http.MaxBytesReader(c.Response(), c.Request().Body, importFileLimit)
	employees, err := readFormFile(c, "employees")
	if err != nil {
		return err
	}
	history, err := readFormFile(c, "history")
	if err != nil {
		return err
	}
	result, err := h.service.Import(c.Request().Context(), employees, history)
	if err != nil {
		return err
	}
	return c.JSON(http.StatusOK, result)
}

func readFormFile(c echo.Context, field string) ([]byte, error) {
	header, err := c.FormFile(field)
	if err != nil {
		if err == http.ErrMissingFile {
			return nil, nil
		}
		return nil, errs.NewError(http.StatusBadRequest, "INVALID_UPLOAD", "expected multipart/form-data with files employees and/or history")
	}
	return readMultipart(header)
}

func readMultipart(header *multipart.FileHeader) ([]byte, error) {
	file, err := header.Open()
	if err != nil {
		return nil, errs.NewError(http.StatusBadRequest, "INVALID_UPLOAD", "cannot read uploaded file")
	}
	defer file.Close()
	data, err := io.ReadAll(io.LimitReader(file, importFileLimit))
	if err != nil {
		return nil, errs.NewError(http.StatusBadRequest, "INVALID_UPLOAD", "cannot read uploaded file")
	}
	return data, nil
}
