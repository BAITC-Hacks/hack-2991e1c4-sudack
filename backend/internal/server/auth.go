package server

import (
	"net/http"
	"strings"

	"github.com/BAITC-Hacks/hack-2991e1c4-sudack/internal/domain/errs"
	"github.com/golang-jwt/jwt/v5"
	"github.com/labstack/echo/v4"
)

type claims struct {
	Role string `json:"role"`
	jwt.RegisteredClaims
}

func authenticate(secret string) echo.MiddlewareFunc {
	return func(next echo.HandlerFunc) echo.HandlerFunc {
		return func(c echo.Context) error {
			header := c.Request().Header.Get("Authorization")
			if !strings.HasPrefix(header, "Bearer ") {
				return errs.NewError(http.StatusUnauthorized, "UNAUTHORIZED", "bearer token required")
			}
			tokenText := strings.TrimPrefix(header, "Bearer ")
			payload := &claims{}
			token, err := jwt.ParseWithClaims(tokenText, payload,
				func(token *jwt.Token) (any, error) { return []byte(secret), nil },
				jwt.WithValidMethods([]string{jwt.SigningMethodHS256.Alg()}),
				jwt.WithExpirationRequired(),
			)
			if err != nil || !token.Valid || payload.Subject == "" ||
				(payload.Role != "employee" && payload.Role != "hr") {
				return errs.NewError(http.StatusUnauthorized, "UNAUTHORIZED", "invalid bearer token")
			}
			c.Set("subject", payload.Subject)
			c.Set("role", payload.Role)
			return next(c)
		}
	}
}
