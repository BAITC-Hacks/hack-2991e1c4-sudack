package handler

import "github.com/BAITC-Hacks/hack-2991e1c4-sudack/internal/service"

type Handler struct {
	service *service.Service
}

func NewHandler(service *service.Service) (*Handler, error) {
	return &Handler{
		service: service,
	}, nil
}
