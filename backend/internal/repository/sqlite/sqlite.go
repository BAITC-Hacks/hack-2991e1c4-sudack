package sqlite

import "database/sql"

type Repository struct {
	db *sql.DB
}

func NewRepository(db *sql.DB) (*Repository, error) {
	return &Repository{
		db: db,
	}, nil
}
