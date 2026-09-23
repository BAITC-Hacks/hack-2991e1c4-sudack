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
		if c.Response().Committed {
			return
		}
		slog.Error(err.Error())

		var domainErr *errs.Error
		if errors.As(err, &domainErr) {
			_ = c.JSON(domainErr.HTTPCode, domainErr)
			return
		}
		var echoErr *echo.HTTPError
		if errors.As(err, &echoErr) {
			_ = c.JSON(echoErr.Code, errs.NewError(echoErr.Code, "HTTP_ERROR", http.StatusText(echoErr.Code)))
			return
		}
		_ = c.JSON(http.StatusInternalServerError,
			errs.NewError(http.StatusInternalServerError, "INTERNAL_SERVER_ERROR", "internal server error"))
	}
}
