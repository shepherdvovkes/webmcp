# Kafka Topics Documentation

This document describes the Kafka topics used in the Court Registry MCP system.

## Overview

Kafka serves as the event log for the entire court registry system, providing:
- **Reproducibility**: Replay events to rebuild the legal universe
- **Versioning**: Track document changes over time
- **Audit trail**: Immutable log of all court document processing
- **Temporal dimension**: Understand when legal truth changed

## Topics

### 1. `court.documents.discovered`

**Purpose**: Published when Change Monitor finds a new or modified document.

**Event Schema**:
```json
{
  "doc_id": "string",
  "case_id": "string",
  "url": "string",
  "discovered_at": "ISO8601 timestamp",
  "hash_hint": "string | null"
}
```

**Published by**: Change Monitor service
**Consumed by**: Fetcher service (optional - can also use direct calls)

---

### 2. `court.documents.fetched`

**Purpose**: Published when a document file is successfully downloaded.

**Event Schema**:
```json
{
  "doc_id": "string",
  "storage_path": "string",
  "sha256": "string",
  "fetched_at": "ISO8601 timestamp"
}
```

**Published by**: Fetcher service
**Consumed by**: Parser service (optional - can also use direct calls)

**Guarantee**: We know exactly what was downloaded and can verify integrity.

---

### 3. `court.documents.parsed`

**Purpose**: Published after successful parsing of a document.

**Event Schema**:
```json
{
  "doc_id": "string",
  "version_id": "string",
  "entities": {
    "court": "string",
    "judge": "string",
    "parties": {
      "plaintiff": ["string"],
      "defendant": ["string"]
    },
    "date": "string"
  },
  "law_refs": ["string"],
  "parsed_at": "ISO8601 timestamp"
}
```

**Published by**: Parser service
**Consumed by**: Database writer, Graph builder, Embedding service

**Represents**: Legal understanding of the document.

---

### 4. `court.documents.failed`

**Purpose**: Published when document processing fails at any stage.

**Event Schema**:
```json
{
  "doc_id": "string",
  "stage": "string",  // 'discovery', 'fetch', 'parse', 'embedding'
  "error": "string",
  "error_details": {
    "url": "string",
    "content_type": "string",
    // ... other context
  },
  "failed_at": "ISO8601 timestamp"
}
```

**Published by**: All services (on error)
**Consumed by**: Alerting system, Retry mechanism

**Use case**: Automatic replay of failed events after fixes.

---

## Event Flow

```
Change Monitor
    ↓ (discovered)
Kafka: court.documents.discovered
    ↓
Fetcher
    ↓ (fetched)
Kafka: court.documents.fetched
    ↓
Parser
    ↓ (parsed)
Kafka: court.documents.parsed
    ↓
Database / Graph / Embeddings
```

## Replay & Reprocessing

All events are stored in Kafka with retention. This allows:

1. **Parser updates**: Replay all `court.documents.fetched` events with new parser
2. **Bug fixes**: Replay failed events after fixing the issue
3. **New features**: Replay events to extract new information
4. **Audit**: Track exactly when documents were processed

## Consumer Groups

Recommended consumer groups:
- `fetcher-pool`: Consumes `discovered` events
- `parser-pool`: Consumes `fetched` events
- `db-writer`: Consumes `parsed` events
- `alerting`: Consumes `failed` events

## Configuration

Kafka settings in `config.py`:
- `kafka_bootstrap_servers`: Kafka broker addresses
- `kafka_enabled`: Enable/disable Kafka (for development)
- `kafka_auto_create_topics`: Auto-create topics if they don't exist

## Docker Setup

Kafka runs in a separate container defined in `docker-compose.yml`:
- **Zookeeper**: Required for Kafka coordination
- **Kafka**: Main message broker
- Both are on the `court-registry-network`

Access from application container: `kafka:9092`
Access from host: `localhost:9092`
