package migrations

import _ "embed"

// InitSQL is the schema used to initialize a new Career Quest database.
//
//go:embed 1_init.sql
var InitSQL string
