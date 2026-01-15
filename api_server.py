"""FastAPI server for HTTP access to MCP functionality."""
from fastapi import FastAPI, Depends, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from database import get_db
from mcp_server import (
    find_cases, search_similar_cases, get_case_details,
    get_document, analyze_judge_patterns
)
from services.metrics import get_metrics, get_metrics_content_type
from config import settings
import logging

logger = logging.getLogger(__name__)

app = FastAPI(title="Court Registry MCP API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request models
class FindCasesRequest(BaseModel):
    plaintiff: Optional[str] = None
    defendant: Optional[str] = None
    law_article: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    outcome: Optional[str] = None
    court: Optional[str] = None
    limit: int = 10


class SearchSimilarRequest(BaseModel):
    query: str
    section_type: Optional[str] = None
    limit: int = 5


class GetCaseRequest(BaseModel):
    case_id: str


class GetDocumentRequest(BaseModel):
    document_version_id: str


class AnalyzeJudgeRequest(BaseModel):
    judge_name: Optional[str] = None
    law_article: Optional[str] = None
    party_type: Optional[str] = None


class TriggerFetchRequest(BaseModel):
    date_from: str
    date_to: Optional[str] = None
    force: bool = False  # Force re-fetch even if already exists


# API endpoints
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "court-registry-mcp"}


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return Response(
        content=get_metrics(),
        media_type=get_metrics_content_type()
    )


@app.post("/api/find_cases")
async def api_find_cases(request: FindCasesRequest, db: Session = Depends(get_db)):
    """Find cases by criteria."""
    try:
        result = await find_cases(db, request.dict())
        return result
    except Exception as e:
        logger.error(f"Error in find_cases: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/search_similar")
async def api_search_similar(request: SearchSimilarRequest, db: Session = Depends(get_db)):
    """Search for similar cases."""
    try:
        result = await search_similar_cases(db, request.dict())
        return result
    except Exception as e:
        logger.error(f"Error in search_similar_cases: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/case_details")
async def api_case_details(request: GetCaseRequest, db: Session = Depends(get_db)):
    """Get case details."""
    try:
        result = await get_case_details(db, request.dict())
        return result
    except Exception as e:
        logger.error(f"Error in get_case_details: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/document")
async def api_document(request: GetDocumentRequest, db: Session = Depends(get_db)):
    """Get document details."""
    try:
        result = await get_document(db, request.dict())
        return result
    except Exception as e:
        logger.error(f"Error in get_document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/analyze_judge")
async def api_analyze_judge(request: AnalyzeJudgeRequest, db: Session = Depends(get_db)):
    """Analyze judge patterns."""
    try:
        result = await analyze_judge_patterns(db, request.dict())
        return result
    except Exception as e:
        logger.error(f"Error in analyze_judge_patterns: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/trigger_fetch")
async def api_trigger_fetch(request: TriggerFetchRequest, db: Session = Depends(get_db)):
    """Trigger fetching cases from registry for a specific date range."""
    try:
        from services.change_monitor import ChangeMonitor
        from services.kafka_client import get_producer
        from datetime import datetime
        from models import DocumentVersion
        
        # Validate date format
        try:
            date_from_obj = datetime.strptime(request.date_from, "%Y-%m-%d")
            date_to_obj = datetime.strptime(request.date_to, "%Y-%m-%d") if request.date_to else None
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid date format: {e}")
        
        # Initialize services
        monitor = ChangeMonitor()
        kafka_producer = get_producer()
        
        try:
            # Search registry for cases in date range
            search_url = f"{settings.court_registry_base_url}{settings.court_registry_search_endpoint}"
            params = {
                "date_from": request.date_from,
                "date_to": request.date_to or datetime.utcnow().strftime("%Y-%m-%d")
            }
            
            logger.info(f"Triggering fetch for date range: {request.date_from} to {params['date_to']}")
            
            # Use monitor's HTTP client to search
            response = await monitor.http_client.get(search_url, params=params)
            response.raise_for_status()
            
            # Parse search results
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text, 'html.parser')
            links = soup.find_all('a', href=True)
            
            discovered_count = 0
            queued_count = 0
            skipped_count = 0
            failed_count = 0
            
            for link in links:
                href = link.get('href', '')
                if '/Document/' in href or '/Case/' in href:
                    full_url = monitor._make_absolute_url(href)
                    doc_id = monitor._extract_doc_id_from_url(full_url)
                    
                    if not doc_id:
                        continue
                    
                    discovered_count += 1
                    
                    # Check if already exists (unless force)
                    if not request.force:
                        existing = db.query(DocumentVersion).filter(
                            DocumentVersion.source_url == full_url
                        ).first()
                        if existing:
                            skipped_count += 1
                            continue
                    
                    # Publish to Kafka for background processing
                    try:
                        kafka_producer.publish_discovered(
                            doc_id=doc_id,
                            case_id='',  # Will be extracted during parsing
                            url=full_url,
                            hash_hint=None
                        )
                        queued_count += 1
                    except Exception as e:
                        logger.error(f"Error queuing document {doc_id}: {e}")
                        failed_count += 1
            
            result = {
                "status": "completed",
                "discovered": discovered_count,
                "queued": queued_count,
                "skipped": skipped_count,
                "failed": failed_count,
                "date_from": request.date_from,
                "date_to": params['date_to'],
                "message": f"Discovered {discovered_count} documents, queued {queued_count} for processing"
            }
            
            return result
            
        finally:
            await monitor.close()
            
    except Exception as e:
        logger.error(f"Error in trigger_fetch: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.mcp_server_host, port=settings.mcp_server_port)
