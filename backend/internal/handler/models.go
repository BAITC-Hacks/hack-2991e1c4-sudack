package handler

type HealthResponse struct {
	Status   string `json:"status" example:"ok"`
	Database string `json:"database" example:"ok"`
}
