FROM python:3.10-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy the project into the image
ADD . /app

# Sync the project into a new environment, using the frozen lockfile
WORKDIR /app
RUN uv sync --frozen

EXPOSE 8080
CMD ["uv", "run", "uvicorn", "main.http_server.app:app", "--port", "${PORT:-8080}","--host", "0.0.0.0"]