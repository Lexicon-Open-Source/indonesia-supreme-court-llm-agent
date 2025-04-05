# Indonesia Supreme Court LLM Agent

This agent can support RAG over the court decision documents

## Prerequisites

- Python 3.10 (via [uv](https://docs.astral.sh/uv/))

After installing uv, run the following command to sync the project:

```bash
uv sync --frozen
```

## Indexing

To index the court decision documents, run the following command:

```bash
uv run main.cli.index_court_docs_summary_content
```

This will rewrite the data under `qdrant_storage` directory`. If data is updated just rebuild the docker image

## Running the HTTP server

To run the HTTP server, run the following command:

```bash
uv run uvicorn main.http_server.app:app --port 8080 --host 0.0.0.0
```

You can configure the port by setting the PORT variable in the .env file:

```
PORT=8080
```

## Running service via docker compose

To run the HTTP server, run the following command:

```bash
docker compose up --build
```
