-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Core Entities
CREATE TABLE IF NOT EXISTS courts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(500) NOT NULL,
    region VARCHAR(200),
    level VARCHAR(50) CHECK (level IN ('local', 'appeal', 'supreme')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS judges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name VARCHAR(500) NOT NULL,
    court_id UUID REFERENCES courts(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS cases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    registry_number VARCHAR(200) UNIQUE NOT NULL,
    court_id UUID REFERENCES courts(id),
    category VARCHAR(200),
    opened_at TIMESTAMP,
    closed_at TIMESTAMP,
    status VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Document & Versioning
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id UUID REFERENCES cases(id),
    type VARCHAR(100) CHECK (type IN ('decision', 'ruling', 'order', 'appeal')),
    current_version_id UUID,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS document_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id),
    version_number INTEGER NOT NULL,
    published_at TIMESTAMP,
    source_url TEXT NOT NULL,
    source_hash VARCHAR(64),
    raw_storage_path TEXT,
    parsed_json JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(document_id, version_number)
);

-- Parties & Roles
CREATE TABLE IF NOT EXISTS parties (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type VARCHAR(50) CHECK (type IN ('person', 'company', 'state')),
    normalized_name VARCHAR(500) NOT NULL,
    tax_id VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS case_parties (
    case_id UUID REFERENCES cases(id),
    party_id UUID REFERENCES parties(id),
    role VARCHAR(50) CHECK (role IN ('plaintiff', 'defendant', 'third_party', 'prosecutor')),
    PRIMARY KEY (case_id, party_id, role)
);

-- Legal Meaning
CREATE TABLE IF NOT EXISTS law_articles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(200) NOT NULL UNIQUE,
    title TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS document_law_refs (
    document_version_id UUID REFERENCES document_versions(id),
    law_article_id UUID REFERENCES law_articles(id),
    PRIMARY KEY (document_version_id, law_article_id)
);

CREATE TABLE IF NOT EXISTS claims (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id UUID REFERENCES cases(id),
    claim_type VARCHAR(200),
    amount DECIMAL(20, 2),
    currency VARCHAR(10),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS decision_outcomes (
    document_version_id UUID REFERENCES document_versions(id),
    party_id UUID REFERENCES parties(id),
    result VARCHAR(50) CHECK (result IN ('won', 'lost', 'partial')),
    amount_awarded DECIMAL(20, 2),
    PRIMARY KEY (document_version_id, party_id)
);

-- Appeals & Lineage
CREATE TABLE IF NOT EXISTS case_relations (
    parent_case_id UUID REFERENCES cases(id),
    child_case_id UUID REFERENCES cases(id),
    relation_type VARCHAR(50) CHECK (relation_type IN ('appeal', 'cassation', 'retrial')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (parent_case_id, child_case_id)
);

CREATE TABLE IF NOT EXISTS document_relations (
    parent_document_version_id UUID REFERENCES document_versions(id),
    child_document_version_id UUID REFERENCES document_versions(id),
    relation_type VARCHAR(50) CHECK (relation_type IN ('amends', 'cancels', 'refers')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (parent_document_version_id, child_document_version_id)
);

-- Parsing & Provenance
CREATE TABLE IF NOT EXISTS parse_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_version_id UUID REFERENCES document_versions(id),
    parser_version VARCHAR(50) NOT NULL,
    parsed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    confidence_score DECIMAL(5, 4)
);

CREATE TABLE IF NOT EXISTS entity_mentions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_version_id UUID REFERENCES document_versions(id),
    entity_type VARCHAR(100),
    entity_id UUID,
    text_span TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Semantic Layer for RAG
CREATE TABLE IF NOT EXISTS document_sections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_version_id UUID REFERENCES document_versions(id),
    section_type VARCHAR(50) CHECK (section_type IN ('FACTS', 'CLAIMS', 'ARGUMENTS', 'LAW_REFERENCES', 'COURT_REASONING', 'DECISION', 'AMOUNTS')),
    order_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS embedding_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    section_id UUID REFERENCES document_sections(id),
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    embedding_vector vector(1536),
    token_count INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS embedding_entity_links (
    embedding_chunk_id UUID REFERENCES embedding_chunks(id),
    entity_type VARCHAR(100),
    entity_id UUID,
    PRIMARY KEY (embedding_chunk_id, entity_type, entity_id)
);

-- Search Index
CREATE TABLE IF NOT EXISTS search_index (
    entity_type VARCHAR(100),
    entity_id UUID,
    text_vector vector(1536),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (entity_type, entity_id)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_cases_registry_number ON cases(registry_number);
CREATE INDEX IF NOT EXISTS idx_documents_case_id ON documents(case_id);
CREATE INDEX IF NOT EXISTS idx_document_versions_document_id ON document_versions(document_id);
CREATE INDEX IF NOT EXISTS idx_document_versions_source_hash ON document_versions(source_hash);
CREATE INDEX IF NOT EXISTS idx_parties_normalized_name ON parties(normalized_name);
CREATE INDEX IF NOT EXISTS idx_case_parties_case_id ON case_parties(case_id);
CREATE INDEX IF NOT EXISTS idx_case_parties_party_id ON case_parties(party_id);
CREATE INDEX IF NOT EXISTS idx_document_sections_document_version_id ON document_sections(document_version_id);
CREATE INDEX IF NOT EXISTS idx_document_sections_section_type ON document_sections(section_type);
CREATE INDEX IF NOT EXISTS idx_embedding_chunks_section_id ON embedding_chunks(section_id);
CREATE INDEX IF NOT EXISTS idx_embedding_chunks_vector ON embedding_chunks USING ivfflat (embedding_vector vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_case_relations_parent ON case_relations(parent_case_id);
CREATE INDEX IF NOT EXISTS idx_case_relations_child ON case_relations(child_case_id);
CREATE INDEX IF NOT EXISTS idx_document_relations_parent ON document_relations(parent_document_version_id);
CREATE INDEX IF NOT EXISTS idx_document_relations_child ON document_relations(child_document_version_id);
CREATE INDEX IF NOT EXISTS idx_parse_runs_document_version ON parse_runs(document_version_id);
CREATE INDEX IF NOT EXISTS idx_entity_mentions_document_version ON entity_mentions(document_version_id);
CREATE INDEX IF NOT EXISTS idx_entity_mentions_entity ON entity_mentions(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_search_index_entity ON search_index(entity_type, entity_id);

-- Update timestamps trigger
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_courts_updated_at BEFORE UPDATE ON courts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_judges_updated_at BEFORE UPDATE ON judges
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_cases_updated_at BEFORE UPDATE ON cases
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_documents_updated_at BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_parties_updated_at BEFORE UPDATE ON parties
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_law_articles_updated_at BEFORE UPDATE ON law_articles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
