# Repository rules for agents

## Endpoint documentation is required

Whenever you add, remove, or change an HTTP endpoint, update `docs/api.md` in the same change. Keep it consistent with the FastAPI request models, response models, and actual error handling. For every endpoint, document:

- HTTP method and path, purpose, and any authentication requirement.
- Required headers, path/query parameters, and JSON request fields, including which are optional and their defaults.
- Success status, response fields, and a realistic request and response example.
- Relevant error status codes, response shape, and when each occurs.
- A command that another developer or agent can run against a local service.

Update the README link or setup instructions when the way to run or call the API changes. Keep automated endpoint tests aligned with the documented contract. Do not publish real API keys or secrets in documentation or examples.
