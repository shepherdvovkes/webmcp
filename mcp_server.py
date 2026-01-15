"""MCP Server for Court Registry queries."""
import asyncio
import json
from typing import Any, Sequence
from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, text
from database import SessionLocal
from models import (
    Case, Document, DocumentVersion, Party, CaseParty, LawArticle,
    DocumentLawRef, DecisionOutcome, DocumentSection, EmbeddingChunk,
    EmbeddingEntityLink, Court, Judge
)
from services.embeddings import EmbeddingService
from config import settings
import logging

logger = logging.getLogger(__name__)

# Create MCP server instance
app = Server("court-registry-mcp")

# Initialize embedding service (lazy initialization)
embedding_service = None


def get_embedding_service():
    """Get or create embedding service."""
    global embedding_service
    if embedding_service is None:
        embedding_service = EmbeddingService()
    return embedding_service


@app.list_tools()
async def handle_list_tools() -> list[Tool]:
    """List available MCP tools."""
    return [
        Tool(
            name="find_cases",
            description="Find court cases by various criteria (plaintiff, defendant, law article, date range, outcome)",
            inputSchema={
                "type": "object",
                "properties": {
                    "plaintiff": {"type": "string", "description": "Name of plaintiff"},
                    "defendant": {"type": "string", "description": "Name of defendant"},
                    "law_article": {"type": "string", "description": "Law article code (e.g., 'CCU 625')"},
                    "date_from": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
                    "date_to": {"type": "string", "description": "End date (YYYY-MM-DD)"},
                    "outcome": {"type": "string", "enum": ["won", "lost", "partial"], "description": "Case outcome"},
                    "court": {"type": "string", "description": "Court name"},
                    "limit": {"type": "integer", "description": "Maximum number of results", "default": 10}
                }
            }
        ),
        Tool(
            name="search_similar_cases",
            description="Search for similar cases using semantic similarity",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Natural language query describing the case"},
                    "section_type": {
                        "type": "string",
                        "enum": ["FACTS", "CLAIMS", "ARGUMENTS", "LAW_REFERENCES", "COURT_REASONING", "DECISION"],
                        "description": "Type of section to search in"
                    },
                    "limit": {"type": "integer", "description": "Maximum number of results", "default": 5}
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="get_case_details",
            description="Get detailed information about a specific case",
            inputSchema={
                "type": "object",
                "properties": {
                    "case_id": {"type": "string", "description": "Case UUID or registry number"}
                },
                "required": ["case_id"]
            }
        ),
        Tool(
            name="get_document",
            description="Get a specific document version with all sections",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_version_id": {"type": "string", "description": "Document version UUID"}
                },
                "required": ["document_version_id"]
            }
        ),
        Tool(
            name="analyze_judge_patterns",
            description="Analyze patterns in judge decisions (e.g., win rate for specific law articles)",
            inputSchema={
                "type": "object",
                "properties": {
                    "judge_name": {"type": "string", "description": "Judge full name"},
                    "law_article": {"type": "string", "description": "Law article code"},
                    "party_type": {"type": "string", "enum": ["person", "company", "state"], "description": "Type of party"}
                }
            }
        )
    ]


@app.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> Sequence[TextContent | ImageContent]:
    """Handle tool calls."""
    db = SessionLocal()
    try:
        if name == "find_cases":
            result = await find_cases(db, arguments)
        elif name == "search_similar_cases":
            result = await search_similar_cases(db, arguments)
        elif name == "get_case_details":
            result = await get_case_details(db, arguments)
        elif name == "get_document":
            result = await get_document(db, arguments)
        elif name == "analyze_judge_patterns":
            result = await analyze_judge_patterns(db, arguments)
        else:
            result = {"error": f"Unknown tool: {name}"}
        
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    except Exception as e:
        logger.error(f"Error in tool {name}: {e}", exc_info=True)
        error_result = {"error": str(e), "tool": name}
        return [TextContent(type="text", text=json.dumps(error_result, ensure_ascii=False, indent=2))]
    finally:
        db.close()


async def find_cases(db: Session, args: dict) -> dict:
    """Find cases by criteria."""
    try:
        # Validate limit
        limit = min(args.get("limit", 10), 100)  # Max 100 results
        
        query = db.query(Case).distinct()
        
        # Filter by plaintiff
        if args.get("plaintiff"):
            query = query.join(CaseParty).join(Party).filter(
                and_(
                    Party.normalized_name.ilike(f"%{args['plaintiff']}%"),
                    CaseParty.role == "plaintiff"
                )
            )
        
        # Filter by defendant
        if args.get("defendant"):
            query = query.join(CaseParty).join(Party).filter(
                and_(
                    Party.normalized_name.ilike(f"%{args['defendant']}%"),
                    CaseParty.role == "defendant"
                )
            )
        
        # Filter by law article
        if args.get("law_article"):
            query = query.join(Document).join(DocumentVersion).join(DocumentLawRef).join(LawArticle).filter(
                LawArticle.code.ilike(f"%{args['law_article']}%")
            )
        
        # Filter by date
        if args.get("date_from"):
            query = query.filter(Case.opened_at >= args["date_from"])
        if args.get("date_to"):
            query = query.filter(Case.opened_at <= args["date_to"])
        
        # Filter by outcome
        if args.get("outcome"):
            query = query.join(Document).join(DocumentVersion).join(DecisionOutcome).filter(
                DecisionOutcome.result == args["outcome"]
            )
        
        # Filter by court
        if args.get("court"):
            query = query.join(Court).filter(Court.name.ilike(f"%{args['court']}%"))
        
        cases = query.limit(limit).all()
        
        results = []
        for case in cases:
            try:
                # Get parties
                parties = db.query(Party, CaseParty.role).join(CaseParty).filter(
                    CaseParty.case_id == case.id
                ).all()
                
                # Get documents
                documents = db.query(Document).filter(Document.case_id == case.id).all()
                
                results.append({
                    "case_id": str(case.id),
                    "registry_number": case.registry_number,
                    "court": str(case.court_id) if case.court_id else None,
                    "category": case.category,
                    "opened_at": case.opened_at.isoformat() if case.opened_at else None,
                    "status": case.status,
                    "parties": [{"name": p.normalized_name, "role": r} for p, r in parties],
                    "document_count": len(documents)
                })
            except Exception as e:
                logger.warning(f"Error processing case {case.id}: {e}")
                continue
        
        return {"cases": results, "count": len(results)}
    except Exception as e:
        logger.error(f"Error in find_cases: {e}", exc_info=True)
        return {"error": str(e), "cases": [], "count": 0}


async def search_similar_cases(db: Session, args: dict) -> dict:
    """Search for similar cases using semantic similarity."""
    try:
        query_text = args.get("query", "").strip()
        if not query_text:
            return {"error": "Query text is required", "similar_cases": [], "count": 0}
        
        section_type = args.get("section_type", "COURT_REASONING")
        limit = min(args.get("limit", 5), 50)  # Max 50 results
        
        # Generate embedding for query
        emb_service = get_embedding_service()
        embeddings = await emb_service.generate_embeddings([query_text])
        if not embeddings or not embeddings[0]:
            return {"error": "Failed to generate embedding for query", "similar_cases": [], "count": 0}
        
        query_embedding = embeddings[0]
        
        # Convert embedding to PostgreSQL vector format
        embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"
        
        # Vector similarity search using pgvector cosine similarity
        sql = text("""
            SELECT 
                ec.id as chunk_id,
                ec.section_id,
                ec.text,
                ec.embedding_vector <=> :query_embedding::vector as distance,
                ds.document_version_id,
                dv.document_id,
                d.case_id
            FROM embedding_chunks ec
            JOIN document_sections ds ON ec.section_id = ds.id
            JOIN document_versions dv ON ds.document_version_id = dv.id
            JOIN documents d ON dv.document_id = d.id
            WHERE ds.section_type = :section_type
            ORDER BY distance
            LIMIT :limit
        """)
        
        result = db.execute(sql, {
            "query_embedding": embedding_str,
            "section_type": section_type,
            "limit": limit
        })
        
        results = []
        for row in result:
            try:
                # Get case details
                case = db.query(Case).filter(Case.id == row.case_id).first()
                if case:
                    results.append({
                        "case_id": str(case.id),
                        "registry_number": case.registry_number,
                        "relevance_score": max(0.0, 1 - float(row.distance)),  # Convert distance to similarity
                        "relevant_text": row.text[:500] if row.text else "",  # First 500 chars
                        "section_type": section_type
                    })
            except Exception as e:
                logger.warning(f"Error processing search result: {e}")
                continue
        
        return {"similar_cases": results, "count": len(results)}
    except Exception as e:
        logger.error(f"Error in search_similar_cases: {e}", exc_info=True)
        return {"error": str(e), "similar_cases": [], "count": 0}


async def get_case_details(db: Session, args: dict) -> dict:
    """Get detailed case information."""
    try:
        case_id = args.get("case_id", "").strip()
        if not case_id:
            return {"error": "case_id is required"}
        
        # Try UUID first, then registry number
        case = None
        try:
            import uuid
            case_uuid = uuid.UUID(case_id)
            case = db.query(Case).filter(Case.id == case_uuid).first()
        except ValueError:
            case = db.query(Case).filter(Case.registry_number == case_id).first()
        
        if not case:
            return {"error": "Case not found"}
        
        # Get court
        court = db.query(Court).filter(Court.id == case.court_id).first()
        
        # Get parties
        parties = db.query(Party, CaseParty.role).join(CaseParty).filter(
            CaseParty.case_id == case.id
        ).all()
        
        # Get documents
        documents = db.query(Document).filter(Document.case_id == case.id).all()
        doc_details = []
        for doc in documents:
            version = db.query(DocumentVersion).filter(
                DocumentVersion.id == doc.current_version_id
            ).first()
            if version:
                doc_details.append({
                    "document_id": str(doc.id),
                    "type": doc.type,
                    "published_at": version.published_at.isoformat() if version.published_at else None,
                    "source_url": version.source_url
                })
        
        return {
            "case_id": str(case.id),
            "registry_number": case.registry_number,
            "court": {
                "id": str(court.id) if court else None,
                "name": court.name if court else None,
                "level": court.level if court else None
            },
            "category": case.category,
            "opened_at": case.opened_at.isoformat() if case.opened_at else None,
            "closed_at": case.closed_at.isoformat() if case.closed_at else None,
            "status": case.status,
            "parties": [{"name": p.normalized_name, "type": p.type, "role": r} for p, r in parties],
            "documents": doc_details
        }
    except Exception as e:
        logger.error(f"Error in get_case_details: {e}", exc_info=True)
        return {"error": str(e)}


async def get_document(db: Session, args: dict) -> dict:
    """Get document with all sections."""
    try:
        doc_version_id_str = args.get("document_version_id", "").strip()
        if not doc_version_id_str:
            return {"error": "document_version_id is required"}
        
        import uuid
        try:
            doc_version_id = uuid.UUID(doc_version_id_str)
        except ValueError:
            return {"error": "Invalid document_version_id format"}
        
        version = db.query(DocumentVersion).filter(DocumentVersion.id == doc_version_id).first()
        if not version:
            return {"error": "Document version not found"}
        
        # Get sections
        sections = db.query(DocumentSection).filter(
            DocumentSection.document_version_id == doc_version_id
        ).order_by(DocumentSection.order_index).all()
        
        section_data = []
        for section in sections:
            section_data.append({
                "section_type": section.section_type,
                "order_index": section.order_index,
                "text": section.text
            })
        
        return {
            "document_version_id": str(version.id),
            "version_number": version.version_number,
            "published_at": version.published_at.isoformat() if version.published_at else None,
            "source_url": version.source_url,
            "parsed_json": version.parsed_json,
            "sections": section_data
        }
    except Exception as e:
        logger.error(f"Error in get_document: {e}", exc_info=True)
        return {"error": str(e)}


async def analyze_judge_patterns(db: Session, args: dict) -> dict:
    """Analyze judge decision patterns."""
    try:
        judge_name = args.get("judge_name")
        law_article = args.get("law_article")
        party_type = args.get("party_type")
        
        query = db.query(DecisionOutcome, DocumentVersion, Judge, Case)
        query = query.join(DocumentVersion, DecisionOutcome.document_version_id == DocumentVersion.id)
        query = query.join(Document, DocumentVersion.document_id == Document.id)
        query = query.join(Case, Document.case_id == Case.id)
        query = query.join(Judge, Case.court_id == Judge.court_id)
        
        if judge_name:
            query = query.filter(Judge.full_name.ilike(f"%{judge_name}%"))
        
        if law_article:
            query = query.join(DocumentLawRef).join(LawArticle).filter(
                LawArticle.code.ilike(f"%{law_article}%")
            )
        
        if party_type:
            query = query.join(Party, DecisionOutcome.party_id == Party.id).filter(
                Party.type == party_type
            )
        
        outcomes = query.all()
        
        # Calculate statistics
        total = len(outcomes)
        won = sum(1 for o, _, _, _ in outcomes if o and o.result == "won")
        lost = sum(1 for o, _, _, _ in outcomes if o and o.result == "lost")
        partial = sum(1 for o, _, _, _ in outcomes if o and o.result == "partial")
        
        return {
            "total_decisions": total,
            "won": won,
            "lost": lost,
            "partial": partial,
            "win_rate": won / total if total > 0 else 0.0,
            "filters": {
                "judge_name": judge_name,
                "law_article": law_article,
                "party_type": party_type
            }
        }
    except Exception as e:
        logger.error(f"Error in analyze_judge_patterns: {e}", exc_info=True)
        return {"error": str(e), "total_decisions": 0, "won": 0, "lost": 0, "partial": 0, "win_rate": 0.0}


async def main():
    """Run MCP server."""
    async with stdio_server() as streams:
        await app.run(
            streams[0],
            streams[1],
            InitializationOptions(
                server_name="court-registry-mcp",
                server_version="1.0.0"
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
