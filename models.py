"""SQLAlchemy models for Court Registry database."""
from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey, DECIMAL, CheckConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
import uuid
from database import Base


class Court(Base):
    __tablename__ = "courts"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(500), nullable=False)
    region = Column(String(200))
    level = Column(String(50))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Judge(Base):
    __tablename__ = "judges"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name = Column(String(500), nullable=False)
    court_id = Column(UUID(as_uuid=True), ForeignKey("courts.id"))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Case(Base):
    __tablename__ = "cases"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    registry_number = Column(String(200), unique=True, nullable=False)
    court_id = Column(UUID(as_uuid=True), ForeignKey("courts.id"))
    category = Column(String(200))
    opened_at = Column(DateTime)
    closed_at = Column(DateTime)
    status = Column(String(100))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Document(Base):
    __tablename__ = "documents"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id"))
    type = Column(String(100))
    current_version_id = Column(UUID(as_uuid=True))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"))
    version_number = Column(Integer, nullable=False)
    published_at = Column(DateTime)
    source_url = Column(Text, nullable=False)
    source_hash = Column(String(64))
    raw_storage_path = Column(Text)
    parsed_json = Column(JSONB)
    created_at = Column(DateTime, server_default=func.now())
    
    __table_args__ = (
        UniqueConstraint('document_id', 'version_number', name='uq_document_version'),
    )


class Party(Base):
    __tablename__ = "parties"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type = Column(String(50))
    normalized_name = Column(String(500), nullable=False)
    tax_id = Column(String(50))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class CaseParty(Base):
    __tablename__ = "case_parties"
    
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id"), primary_key=True)
    party_id = Column(UUID(as_uuid=True), ForeignKey("parties.id"), primary_key=True)
    role = Column(String(50), primary_key=True)


class LawArticle(Base):
    __tablename__ = "law_articles"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String(200), unique=True, nullable=False)
    title = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class DocumentLawRef(Base):
    __tablename__ = "document_law_refs"
    
    document_version_id = Column(UUID(as_uuid=True), ForeignKey("document_versions.id"), primary_key=True)
    law_article_id = Column(UUID(as_uuid=True), ForeignKey("law_articles.id"), primary_key=True)


class Claim(Base):
    __tablename__ = "claims"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id"))
    claim_type = Column(String(200))
    amount = Column(DECIMAL(20, 2))
    currency = Column(String(10))
    created_at = Column(DateTime, server_default=func.now())


class DecisionOutcome(Base):
    __tablename__ = "decision_outcomes"
    
    document_version_id = Column(UUID(as_uuid=True), ForeignKey("document_versions.id"), primary_key=True)
    party_id = Column(UUID(as_uuid=True), ForeignKey("parties.id"), primary_key=True)
    result = Column(String(50))
    amount_awarded = Column(DECIMAL(20, 2))


class DocumentSection(Base):
    __tablename__ = "document_sections"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_version_id = Column(UUID(as_uuid=True), ForeignKey("document_versions.id"))
    section_type = Column(String(50))
    order_index = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class EmbeddingChunk(Base):
    __tablename__ = "embedding_chunks"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    section_id = Column(UUID(as_uuid=True), ForeignKey("document_sections.id"))
    chunk_index = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    embedding_vector = Column(Vector(1536))
    token_count = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())


class EmbeddingEntityLink(Base):
    __tablename__ = "embedding_entity_links"
    
    embedding_chunk_id = Column(UUID(as_uuid=True), ForeignKey("embedding_chunks.id"), primary_key=True)
    entity_type = Column(String(100), primary_key=True)
    entity_id = Column(UUID(as_uuid=True), primary_key=True)


class CaseRelation(Base):
    __tablename__ = "case_relations"
    
    parent_case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id"), primary_key=True)
    child_case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id"), primary_key=True)
    relation_type = Column(String(50))  # appeal, cassation, retrial
    created_at = Column(DateTime, server_default=func.now())


class DocumentRelation(Base):
    __tablename__ = "document_relations"
    
    parent_document_version_id = Column(UUID(as_uuid=True), ForeignKey("document_versions.id"), primary_key=True)
    child_document_version_id = Column(UUID(as_uuid=True), ForeignKey("document_versions.id"), primary_key=True)
    relation_type = Column(String(50))  # amends, cancels, refers
    created_at = Column(DateTime, server_default=func.now())


class ParseRun(Base):
    __tablename__ = "parse_runs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_version_id = Column(UUID(as_uuid=True), ForeignKey("document_versions.id"))
    parser_version = Column(String(50), nullable=False)
    parsed_at = Column(DateTime, server_default=func.now())
    confidence_score = Column(DECIMAL(5, 4))


class EntityMention(Base):
    __tablename__ = "entity_mentions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_version_id = Column(UUID(as_uuid=True), ForeignKey("document_versions.id"))
    entity_type = Column(String(100))  # judge, party, law, amount
    entity_id = Column(UUID(as_uuid=True))
    text_span = Column(Text)
    created_at = Column(DateTime, server_default=func.now())


class SearchIndex(Base):
    __tablename__ = "search_index"
    
    entity_type = Column(String(100), primary_key=True)
    entity_id = Column(UUID(as_uuid=True), primary_key=True)
    text_vector = Column(Vector(1536))
    created_at = Column(DateTime, server_default=func.now())
