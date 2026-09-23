package server

import (
	"errors"
	"log/slog"
	"net/http"

	"github.com/BAITC-Hacks/hack-2991e1c4-sudack/internal/domain/errs"
	"github.com/labstack/echo/v4"
)

func newEchoErrorHandler() echo.HTTPErrorHandler {
	return func(err error, c echo.Context) {
		resp := &errs.Error{
			HTTPCode: http.StatusInternalServerError,
			Code:     "INTERNAL_SERVER_ERROR",
			Message:  err.Error(),
		}

		slog.Error(err.Error())

		var e *errs.Error
		if errors.As(err, &e) {
			resp = e
		} else {
			resp.Message = err.Error()
		}

		_ = c.JSON(resp.HTTPCode, resp)
	}
}
