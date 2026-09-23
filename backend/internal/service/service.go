package service

import "github.com/BAITC-Hacks/hack-2991e1c4-sudack/internal/repository/sqlite"

type Service struct {
	repository *sqlite.Repository
}

func NewService(repository *sqlite.Repository) (*Service, error) {
	return &Service{
		repository: repository,
	}, nil
}
