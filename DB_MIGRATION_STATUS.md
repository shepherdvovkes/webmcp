# Database Migration Status

## Overview

This document describes the database migration and schema setup for the Court Registry MCP system.

## Migration Strategy

The system uses a **dual approach** for database initialization:

1. **SQL Script (init_db.sql)**: Executed automatically when PostgreSQL container is first initialized
   - Location: `./init_db.sql`
   - Mounted to: `/docker-entrypoint-initdb.d/init_db.sql` in docker-compose.yml
   - Runs only on first database initialization (when data volume is empty)

2. **SQLAlchemy Models (models.py)**: Used as fallback to create missing tables
   - Location: `./models.py`
   - Called via `Base.metadata.create_all(bind=engine)` in `main.py`
   - Runs on every application startup if tables don't exist

## Schema Components

### Tables (19 total)
All tables are defined in both `init_db.sql` and `models.py`:

1. `courts` - Court information
2. `judges` - Judge information
3. `cases` - Court cases
4. `documents` - Document metadata
5. `document_versions` - Document versioning
6. `parties` - Legal parties (plaintiffs, defendants, etc.)
7. `case_parties` - Case-party relationships
8. `law_articles` - Legal articles/codes
9. `document_law_refs` - Document-law article references
10. `claims` - Legal claims
11. `decision_outcomes` - Court decision outcomes
12. `case_relations` - Case relationships (appeals, etc.)
13. `document_relations` - Document relationships
14. `parse_runs` - Parser execution records
15. `entity_mentions` - Entity mentions in documents
16. `document_sections` - Document text sections
17. `embedding_chunks` - Text chunks with embeddings
18. `embedding_entity_links` - Links between embeddings and entities
19. `search_index` - Search index with vector embeddings

### Extensions
- **pgvector**: Required for vector similarity search
  - Enabled in `init_db.sql`: `CREATE EXTENSION IF NOT EXISTS vector;`

### Indexes (19 total)
All performance-critical indexes are created in `init_db.sql`:
- Primary key indexes (automatic)
- Foreign key indexes
- Search indexes (registry_number, normalized_name, etc.)
- Vector similarity index on `embedding_chunks.embedding_vector`

### Triggers (6 total)
Update timestamp triggers for:
- `courts`
- `judges`
- `cases`
- `documents`
- `parties`
- `law_articles`

### Functions (1 total)
- `update_updated_at_column()` - Updates `updated_at` timestamp on row updates

## Verification

### Manual Verification

**Recommended: Run via Docker (on remote server)**
```bash
# SSH to server first, then:
cd ~/court-registry-mcp
docker-compose exec court-registry-mcp python3 verify_db_schema.py
```

**Alternative: Run locally (requires dependencies)**
```bash
# Install dependencies first:
pip install -r requirements.txt

# Then run:
python3 verify_db_schema.py
```

**Note**: The script requires database access, so it must be run where the database is accessible (either in the Docker container or with proper network access).

### What Gets Checked
1. ✓ pgvector extension enabled
2. ✓ All 19 tables exist
3. ✓ All 19 indexes exist
4. ✓ All 6 triggers exist
5. ✓ Update function exists
6. ✓ Critical columns (vector types) exist
7. ✓ Key constraints exist

## Deployment Notes

### First Deployment
- `init_db.sql` will run automatically when PostgreSQL container starts for the first time
- All tables, indexes, triggers, and functions will be created

### Subsequent Deployments
- `init_db.sql` will NOT run again (database already initialized)
- Application will check for missing tables via SQLAlchemy on startup
- Missing tables will be created automatically
- **Note**: Indexes, triggers, and functions from `init_db.sql` will NOT be recreated if missing

### Manual Migration
If you need to apply migrations manually:

```bash
# Connect to database
docker-compose exec postgres psql -U court_user -d court_registry

# Or run init_db.sql manually
docker-compose exec -T postgres psql -U court_user -d court_registry < init_db.sql
```

## Known Issues

### Schema Discrepancies Fixed
- ✅ `search_index.created_at` - Added to `init_db.sql` to match `models.py`

### Limitations
- SQLAlchemy `create_all()` does NOT create:
  - Indexes (except primary/unique constraints)
  - Triggers
  - Functions
  - Extensions (pgvector)
  
  These must be created via `init_db.sql` or manual SQL.

## Recommendations

1. **Always verify schema after deployment**: Run `verify_db_schema.py`
2. **For production**: Consider using a proper migration tool (Alembic) for versioned migrations
3. **Monitor**: Check application logs for database initialization messages
4. **Backup**: Ensure database backups include schema and data

## Files

- `init_db.sql` - Complete database schema SQL
- `models.py` - SQLAlchemy ORM models
- `database.py` - Database connection setup
- `verify_db_schema.py` - Schema verification script
- `main.py` - Application entry point (calls `init_database()`)
