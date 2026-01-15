#!/usr/bin/env python3
"""Verify database schema and migrations are properly executed."""
import sys
import os

# Check if we're in the right environment
try:
    from sqlalchemy import text, inspect
    from database import engine, Base
    from models import *
    from config import settings
except ImportError as e:
    print("Error: Missing required dependencies.")
    print(f"Details: {e}")
    print("\nThis script should be run:")
    print("  1. Inside the Docker container: docker-compose exec court-registry-mcp python3 verify_db_schema.py")
    print("  2. Or locally after installing dependencies: pip install -r requirements.txt")
    sys.exit(1)

# Expected tables from init_db.sql
EXPECTED_TABLES = [
    'courts',
    'judges',
    'cases',
    'documents',
    'document_versions',
    'parties',
    'case_parties',
    'law_articles',
    'document_law_refs',
    'claims',
    'decision_outcomes',
    'case_relations',
    'document_relations',
    'parse_runs',
    'entity_mentions',
    'document_sections',
    'embedding_chunks',
    'embedding_entity_links',
    'search_index'
]

# Expected indexes (key ones)
EXPECTED_INDEXES = [
    'idx_cases_registry_number',
    'idx_documents_case_id',
    'idx_document_versions_document_id',
    'idx_document_versions_source_hash',
    'idx_parties_normalized_name',
    'idx_case_parties_case_id',
    'idx_case_parties_party_id',
    'idx_document_sections_document_version_id',
    'idx_document_sections_section_type',
    'idx_embedding_chunks_section_id',
    'idx_embedding_chunks_vector',
    'idx_case_relations_parent',
    'idx_case_relations_child',
    'idx_document_relations_parent',
    'idx_document_relations_child',
    'idx_parse_runs_document_version',
    'idx_entity_mentions_document_version',
    'idx_entity_mentions_entity',
    'idx_search_index_entity'
]

# Expected triggers
EXPECTED_TRIGGERS = [
    'update_courts_updated_at',
    'update_judges_updated_at',
    'update_cases_updated_at',
    'update_documents_updated_at',
    'update_parties_updated_at',
    'update_law_articles_updated_at'
]

# Expected function
EXPECTED_FUNCTIONS = [
    'update_updated_at_column'
]


def check_pgvector_extension():
    """Check if pgvector extension is enabled."""
    print("Checking pgvector extension...")
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT EXISTS(
                SELECT 1 FROM pg_extension WHERE extname = 'vector'
            ) as exists;
        """))
        exists = result.scalar()
        if exists:
            print("  ✓ pgvector extension is enabled")
            return True
        else:
            print("  ✗ pgvector extension is NOT enabled")
            return False


def check_tables():
    """Check if all expected tables exist."""
    print("\nChecking tables...")
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    expected_tables = set(EXPECTED_TABLES)
    
    missing_tables = expected_tables - existing_tables
    extra_tables = existing_tables - expected_tables
    
    all_good = True
    for table in EXPECTED_TABLES:
        if table in existing_tables:
            print(f"  ✓ Table '{table}' exists")
        else:
            print(f"  ✗ Table '{table}' is MISSING")
            all_good = False
    
    if extra_tables:
        print(f"\n  Note: Found {len(extra_tables)} extra tables: {', '.join(extra_tables)}")
    
    return all_good


def check_indexes():
    """Check if all expected indexes exist."""
    print("\nChecking indexes...")
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT indexname 
            FROM pg_indexes 
            WHERE schemaname = 'public' 
            AND indexname LIKE 'idx_%'
            ORDER BY indexname;
        """))
        existing_indexes = {row[0] for row in result}
    
    all_good = True
    for index in EXPECTED_INDEXES:
        if index in existing_indexes:
            print(f"  ✓ Index '{index}' exists")
        else:
            print(f"  ✗ Index '{index}' is MISSING")
            all_good = False
    
    return all_good


def check_triggers():
    """Check if all expected triggers exist."""
    print("\nChecking triggers...")
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT trigger_name 
            FROM information_schema.triggers 
            WHERE trigger_schema = 'public'
            ORDER BY trigger_name;
        """))
        existing_triggers = {row[0] for row in result}
    
    all_good = True
    for trigger in EXPECTED_TRIGGERS:
        if trigger in existing_triggers:
            print(f"  ✓ Trigger '{trigger}' exists")
        else:
            print(f"  ✗ Trigger '{trigger}' is MISSING")
            all_good = False
    
    return all_good


def check_functions():
    """Check if all expected functions exist."""
    print("\nChecking functions...")
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT routine_name 
            FROM information_schema.routines 
            WHERE routine_schema = 'public'
            AND routine_type = 'FUNCTION'
            ORDER BY routine_name;
        """))
        existing_functions = {row[0] for row in result}
    
    all_good = True
    for func in EXPECTED_FUNCTIONS:
        if func in existing_functions:
            print(f"  ✓ Function '{func}' exists")
        else:
            print(f"  ✗ Function '{func}' is MISSING")
            all_good = False
    
    return all_good


def check_table_columns():
    """Check critical table columns."""
    print("\nChecking critical table columns...")
    with engine.connect() as conn:
        # Check if embedding_chunks has vector column
        result = conn.execute(text("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'embedding_chunks' 
            AND column_name = 'embedding_vector';
        """))
        if result.fetchone():
            print("  ✓ embedding_chunks.embedding_vector column exists")
        else:
            print("  ✗ embedding_chunks.embedding_vector column is MISSING")
            return False
        
        # Check if search_index has vector column
        result = conn.execute(text("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'search_index' 
            AND column_name = 'text_vector';
        """))
        if result.fetchone():
            print("  ✓ search_index.text_vector column exists")
        else:
            print("  ✗ search_index.text_vector column is MISSING")
            return False
    
    return True


def check_constraints():
    """Check if key constraints exist."""
    print("\nChecking constraints...")
    with engine.connect() as conn:
        # Check unique constraint on document_versions
        result = conn.execute(text("""
            SELECT constraint_name 
            FROM information_schema.table_constraints 
            WHERE table_name = 'document_versions' 
            AND constraint_type = 'UNIQUE'
            AND constraint_name LIKE '%document_version%';
        """))
        if result.fetchone():
            print("  ✓ document_versions unique constraint exists")
        else:
            print("  ✗ document_versions unique constraint is MISSING")
            return False
    
    return True


def main():
    """Run all checks."""
    print("=" * 60)
    print("Database Schema Verification")
    print("=" * 60)
    print(f"Database: {settings.postgres_db}")
    print(f"Host: {settings.postgres_host}:{settings.postgres_port}")
    print("=" * 60)
    
    results = []
    
    # Run all checks
    results.append(("pgvector extension", check_pgvector_extension()))
    results.append(("tables", check_tables()))
    results.append(("indexes", check_indexes()))
    results.append(("triggers", check_triggers()))
    results.append(("functions", check_functions()))
    results.append(("table columns", check_table_columns()))
    results.append(("constraints", check_constraints()))
    
    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    
    all_passed = True
    for check_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{check_name:30s} {status}")
        if not passed:
            all_passed = False
    
    print("=" * 60)
    
    if all_passed:
        print("\n✓ All database migrations and schemas are properly created!")
        return 0
    else:
        print("\n✗ Some database migrations or schemas are missing!")
        print("\nTo fix, ensure init_db.sql is executed or run:")
        print("  Base.metadata.create_all(bind=engine)")
        return 1


if __name__ == "__main__":
    sys.exit(main())
