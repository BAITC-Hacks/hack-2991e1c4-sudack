package main

import (
	"flag"
	"fmt"
	"log"
	"os"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

type claims struct {
	Role string `json:"role"`
	jwt.RegisteredClaims
}

func main() {
	role := flag.String("role", "employee", "employee or hr")
	employeeID := flag.String("employee", "", "employee ID for an employee token")
	flag.Parse()

	secret := os.Getenv("AUTH_SECRET")
	if secret == "" {
		secret = "careerquest-local-demo-secret"
	}
	if *role != "employee" && *role != "hr" {
		log.Fatal("role must be employee or hr")
	}
	subject := *employeeID
	if *role == "hr" {
		subject = "hr"
	} else if subject == "" {
		log.Fatal("-employee is required for employee tokens")
	}
	payload := claims{
		Role: *role,
		RegisteredClaims: jwt.RegisteredClaims{
			Subject:   subject,
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(24 * time.Hour)),
		},
	}
	signed, err := jwt.NewWithClaims(jwt.SigningMethodHS256, payload).SignedString([]byte(secret))
	if err != nil {
		log.Fatal(err)
	}
	fmt.Println(signed)
}
