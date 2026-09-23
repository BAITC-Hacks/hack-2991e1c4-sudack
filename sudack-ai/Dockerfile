FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.8.20 /uv /bin/uv
WORKDIR /service

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev

COPY app ./app
COPY main.py ./main.py

EXPOSE 8001
CMD ["uv", "run", "--no-sync", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
