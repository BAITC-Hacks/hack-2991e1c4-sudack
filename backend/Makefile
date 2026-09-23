BIN_DIR=${CURDIR}/.local/bin

.PHONY: install-bins
install-bins:
	GOBIN=$(BIN_DIR) go install github.com/sqlc-dev/sqlc/cmd/sqlc@latest
	GOBIN=$(BIN_DIR) go install github.com/swaggo/swag/cmd/swag@latest

.PHONY: swag
swag:
	$(BIN_DIR)/swag init --parseDependency --parseInternal --generalInfo ./cmd/main.go

.PHONY: sqlc
sqlc:
	$(BIN_DIR)/sqlc generate -f ./internal/repository/sqlite/sqlc.yaml
