package service

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/BAITC-Hacks/hack-2991e1c4-sudack/internal/domain/errs"
	"github.com/BAITC-Hacks/hack-2991e1c4-sudack/internal/repository/sqlite"
)

// aiTimeout must exceed the AI service's own LLM budget (LLM_TIMEOUT, 9 s by default) so a slow
// but successful explanation is not cut off here; the brief allows 10 s for an AI answer.
const aiTimeout = 12 * time.Second

type Service struct {
	repository *sqlite.Repository
	aiURL      string
	client     *http.Client
}

func NewService(repository *sqlite.Repository, aiURL string) (*Service, error) {
	return &Service{
		repository: repository,
		aiURL:      strings.TrimRight(aiURL, "/"),
		client:     &http.Client{Timeout: aiTimeout},
	}, nil
}

func (s *Service) callAI(ctx context.Context, path string, input any) (json.RawMessage, error) {
	body, err := json.Marshal(input)
	if err != nil {
		return nil, fmt.Errorf("encode AI request: %w", err)
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, s.aiURL+path, bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("create AI request: %w", err)
	}
	request.Header.Set("Content-Type", "application/json")
	response, err := s.client.Do(request)
	if err != nil {
		return nil, fmt.Errorf("%w: %v", errs.NewError(http.StatusServiceUnavailable, "AI_UNAVAILABLE", "recommendation service unavailable"), err)
	}
	defer response.Body.Close()
	data, err := io.ReadAll(io.LimitReader(response.Body, 8<<20))
	if err != nil {
		return nil, fmt.Errorf("read AI response: %w", err)
	}
	if response.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("%w: AI returned HTTP %d: %s",
			errs.NewError(http.StatusBadGateway, "AI_BAD_RESPONSE", "recommendation service rejected the request"),
			response.StatusCode, string(data))
	}
	if !json.Valid(data) {
		return nil, errs.NewError(http.StatusBadGateway, "AI_BAD_RESPONSE", "recommendation service returned invalid JSON")
	}
	return data, nil
}
