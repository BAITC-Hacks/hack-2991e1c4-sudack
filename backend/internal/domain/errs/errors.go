package errs

import (
	"net/http"
)

type Error struct {
	HTTPCode int    `json:"-"`
	Code     string `json:"code"`
	Message  string `json:"message"`
}

func (e *Error) Error() string {
	return e.Message
}

func NewError(httpCode int, code string, message string) *Error {
	return &Error{
		HTTPCode: httpCode,
		Code:     code,
		Message:  message,
	}
}

var (
	ErrInvalidParameter = NewError(http.StatusBadRequest, "INVALID_PARAMETER", "invalid parameter")
)
