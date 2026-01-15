# Court Registry MCP Server

MCP (Model Context Protocol) server for Ukrainian court registry (`reyestr.court.gov.ua`).

## Features

- **Change Monitoring**: Automatically detects new and modified court documents
- **Document Fetching**: Downloads HTML/PDF documents with retry logic
- **Structured Parsing**: Extracts structured data from court documents
- **Versioning**: Maintains complete version history of all documents
- **Semantic Search**: RAG-based search using OpenAI embeddings
- **MCP API**: Exposes query tools for LLM integration
- **REST API**: HTTP endpoints for programmatic access

## Architecture

```
┌─────────────────────────────────────┐
│ Court Registry MCP Server           │
│                                     │
│  ┌───────────┐                      │
│  │ Change    │  → Discovery         │
│  │ Monitor   │                      │
│  └─────┬─────┘                      │
│        ↓                             │
│  ┌───────────┐   ┌──────────────┐   │
│  │ Fetcher   │ → │ Storage      │   │
│  │ Pool      │   │ (MinIO)      │   │
│  └─────┬─────┘   └──────────────┘   │
│        ↓                             │
│  ┌──────────────┐                   │
│  │ Parser       │ → structured JSON │
│  └─────┬────────┘                   │
│        ↓                             │
│  ┌──────────────┐                   │
│  │ PostgreSQL   │                   │
│  │ + pgvector   │                   │
│  └─────┬────────┘                   │
│        ↓                             │
│  ┌──────────────┐                   │
│  │ Embeddings   │ → OpenAI API      │
│  └─────┬────────┘                   │
│        ↓                             │
│        MCP Query API                 │
└─────────────────────────────────────┘
```

## Setup

### 1. Environment Configuration

Copy `.env.example` to `.env` and fill in the required values:

```bash
cp .env.example .env
```

Required configuration:
- `OPENAI_API_KEY`: Your OpenAI API key
- `POSTGRES_PASSWORD`: Database password
- `REDIS_PASSWORD`: Redis password (optional)
- `SECRET_KEY`: Secret key for security

### 2. Docker Compose

Start all services:

```bash
docker-compose up -d
```

This will start:
- PostgreSQL with pgvector extension
- Redis
- Court Registry MCP Server with MinIO (all components in one container)
  - MinIO storage server (ports 9000, 9001)
  - API server (port 8000)

### 3. Manual Setup (without Docker)

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Start PostgreSQL and Redis

3. Run database migrations:
```bash
psql -U court_user -d court_registry -f init_db.sql
```

4. Start the server:
```bash
python main.py
```

## Usage

### MCP Protocol

The server exposes MCP tools that can be used by LLM clients:

- `find_cases`: Find cases by plaintiff, defendant, law article, date range, outcome
- `search_similar_cases`: Semantic search for similar cases
- `get_case_details`: Get detailed case information
- `get_document`: Get document with all sections
- `analyze_judge_patterns`: Analyze judge decision patterns

### REST API

The server also exposes HTTP endpoints:

- `GET /health`: Health check
- `POST /api/find_cases`: Find cases
- `POST /api/search_similar`: Semantic search
- `POST /api/case_details`: Get case details
- `POST /api/document`: Get document
- `POST /api/analyze_judge`: Analyze judge patterns

Example:

```bash
curl -X POST http://localhost:8000/api/find_cases \
  -H "Content-Type: application/json" \
  -d '{
    "plaintiff": "Rozetka",
    "law_article": "Consumer Protection",
    "limit": 10
  }'
```

## Database Schema

The database includes:

- **Core Entities**: Cases, Courts, Judges, Parties
- **Document Versioning**: Documents with immutable version history
- **Legal Graph**: Relationships between cases, parties, and law articles
- **Semantic Layer**: Document sections with embeddings for RAG
- **Search Index**: Vector embeddings for similarity search

See `init_db.sql` for complete schema.

## Services

### Change Monitor

Runs every 10 minutes (configurable) to discover new/changed documents.

### Fetcher Pool

Concurrent workers (default: 10) download documents with retry logic.

### Parser

Extracts structured data:
- Case metadata
- Parties (plaintiff/defendant)
- Claims and amounts
- Law references
- Court reasoning
- Decisions

### Embedding Service

Generates embeddings using OpenAI API for semantic search.

## Configuration

All configuration is done via environment variables. See `.env.example` for all options.

## Development

The project structure:

```
.
├── main.py              # Entry point
├── config.py           # Configuration
├── database.py          # Database connection
├── models.py            # SQLAlchemy models
├── mcp_server.py        # MCP protocol server
├── api_server.py        # FastAPI HTTP server
├── services/
│   ├── change_monitor.py
│   ├── fetcher.py
│   ├── parser.py
│   └── embeddings.py
├── Dockerfile
├── docker-compose.yml
└── init_db.sql
```

## License

MIT
