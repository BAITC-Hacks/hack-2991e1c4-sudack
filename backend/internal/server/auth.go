package server

import (
	"net/http"
	"regexp"
	"strings"
	"time"

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

var employeeIDPattern = regexp.MustCompile(`^[A-Za-z0-9_-]{1,32}$`)

// demoToken issues a signed demo token from the login screen: the jury picks a role and an
// employee, no token copying. Enabled by DEMO_AUTH; real deployments issue tokens elsewhere.
func demoToken(secret string) echo.HandlerFunc {
	return func(c echo.Context) error {
		var body struct {
			Role       string `json:"role"`
			EmployeeID string `json:"employee_id"`
		}
		if err := c.Bind(&body); err != nil {
			return errs.ErrInvalidParameter
		}
		subject := "hr"
		switch body.Role {
		case "hr":
		case "employee":
			if !employeeIDPattern.MatchString(body.EmployeeID) {
				return errs.NewError(http.StatusBadRequest, "INVALID_PARAMETER", "employee_id is required for an employee token")
			}
			subject = body.EmployeeID
		default:
			return errs.NewError(http.StatusBadRequest, "INVALID_PARAMETER", "role must be employee or hr")
		}
		expires := time.Now().Add(24 * time.Hour)
		signed, err := jwt.NewWithClaims(jwt.SigningMethodHS256, claims{
			Role: body.Role,
			RegisteredClaims: jwt.RegisteredClaims{
				Subject:   subject,
				IssuedAt:  jwt.NewNumericDate(time.Now()),
				ExpiresAt: jwt.NewNumericDate(expires),
			},
		}).SignedString([]byte(secret))
		if err != nil {
			return err
		}
		return c.JSON(http.StatusOK, map[string]any{
			"access_token": signed, "token_type": "bearer", "role": body.Role, "subject": subject,
			"expires_at": expires.UTC().Format(time.RFC3339),
		})
	}
}
