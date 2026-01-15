"""Main entry point - runs all services in a single container."""
import asyncio
import logging
import signal
import sys
import os
import subprocess
import time
from multiprocessing import Process
from pathlib import Path
from config import settings
from database import engine, Base
from services.change_monitor import ChangeMonitor
from services.fetcher import FetcherPool
from services.parser import Parser
from services.embeddings import EmbeddingService
from services.kafka_client import get_producer, close_producer
from services.metrics import (
    documents_discovered, documents_fetched, documents_parsed,
    document_processing_duration, active_document_processing,
    embeddings_generated, embedding_generation_duration
)
from api_server import app
import uvicorn

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def init_database():
    """Initialize database tables."""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables initialized")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")


def run_minio_server():
    """Run MinIO server."""
    minio_data_dir = Path("/app/minio-data")
    minio_data_dir.mkdir(parents=True, exist_ok=True)
    
    # Parse MinIO endpoint to get port
    endpoint = settings.minio_endpoint
    if ':' in endpoint:
        _, port = endpoint.split(':')
    else:
        port = "9000"
    
    # Set MinIO environment variables
    env = os.environ.copy()
    env['MINIO_ROOT_USER'] = settings.minio_access_key
    env['MINIO_ROOT_PASSWORD'] = settings.minio_secret_key
    
    # Start MinIO server (listen on all interfaces inside container)
    cmd = [
        "/usr/local/bin/minio",
        "server",
        str(minio_data_dir),
        "--address", f"0.0.0.0:{port}",
        "--console-address", f"0.0.0.0:9001"
    ]
    
    logger.info(f"Starting MinIO server on 0.0.0.0:{port}")
    try:
        subprocess.run(cmd, env=env, check=True)
    except Exception as e:
        logger.error(f"MinIO server error: {e}")


def run_api_server():
    """Run FastAPI server."""
    uvicorn.run(
        app,
        host=settings.mcp_server_host,
        port=settings.mcp_server_port,
        log_level=settings.log_level.lower()
    )


async def run_background_services():
    """Run background services (monitor, fetcher, parser, embeddings)."""
    from database import SessionLocal
    from models import DocumentVersion, Document, Case, DocumentSection, EmbeddingChunk
    from services.parser import Parser
    from services.embeddings import EmbeddingService
    import uuid
    
    monitor = None
    fetcher = None
    parser = None
    embedding_service = None
    
    try:
        # Initialize services
        monitor = ChangeMonitor()
        fetcher = FetcherPool()
        parser = Parser()
        embedding_service = EmbeddingService()
        
        # Start discovery loop (runs continuously)
        discovery_task = asyncio.create_task(run_discovery_loop(monitor, fetcher, parser, embedding_service))
        
        # Start reconciliation loop (runs periodically)
        reconciliation_task = asyncio.create_task(run_reconciliation_loop(monitor, fetcher, parser, embedding_service))
        
        # Wait for both tasks
        await asyncio.gather(discovery_task, reconciliation_task)
        
    except Exception as e:
        logger.error(f"Error in background services: {e}", exc_info=True)
    finally:
        if monitor:
            await monitor.close()
        if fetcher:
            await fetcher.close()
        close_producer()


async def run_discovery_loop(monitor, fetcher, parser, embedding_service):
    """Run discovery loop to find new documents."""
    from database import SessionLocal
    from models import DocumentVersion, Document, Case, DocumentSection, EmbeddingChunk
    import uuid
    
    kafka_producer = get_producer()
    
    while True:
        try:
            db = SessionLocal()
            try:
                discovered = await monitor.discover_documents(db)
                
                if discovered:
                    logger.info(f"Discovered {len(discovered)} documents, processing...")
                    documents_discovered.inc(len(discovered))
                    
                    # Process discovered documents
                    for doc_info in discovered:
                        doc_id = doc_info.get('doc_id') or str(uuid.uuid4())
                        case_id = doc_info.get('case_id', '')
                        url = doc_info.get('url', '')
                        hash_hint = doc_info.get('hash_hint')
                        
                        # Publish discovery event to Kafka
                        try:
                            kafka_producer.publish_discovered(
                                doc_id=doc_id,
                                case_id=case_id,
                                url=url,
                                hash_hint=hash_hint
                            )
                        except Exception as e:
                            logger.warning(f"Failed to publish discovery event: {e}")
                        
                        try:
                            await process_discovered_document(
                                db, doc_info, fetcher, parser, embedding_service, kafka_producer
                            )
                        except Exception as e:
                            logger.error(f"Error processing document {doc_id}: {e}", exc_info=True)
                            # Publish failure event
                            try:
                                kafka_producer.publish_failed(
                                    doc_id=doc_id,
                                    stage='discovery',
                                    error=str(e),
                                    error_details={'url': url}
                                )
                            except Exception as kafka_err:
                                logger.warning(f"Failed to publish failure event: {kafka_err}")
                    
                    db.commit()
                
            finally:
                db.close()
            
            await asyncio.sleep(settings.discovery_interval_minutes * 60)
            
        except Exception as e:
            logger.error(f"Error in discovery cycle: {e}", exc_info=True)
            await asyncio.sleep(60)  # Wait before retry


async def run_reconciliation_loop(monitor, fetcher, parser, embedding_service):
    """Run reconciliation loop to detect changed documents."""
    from database import SessionLocal
    from models import DocumentVersion
    from sqlalchemy import and_
    
    while True:
        try:
            await asyncio.sleep(settings.reconciliation_interval_hours * 3600)
            
            db = SessionLocal()
            try:
                # Get all document versions to check
                versions = db.query(DocumentVersion).filter(
                    DocumentVersion.source_hash.isnot(None)
                ).limit(100).all()  # Check in batches
                
                logger.info(f"Checking {len(versions)} documents for changes...")
                
                changed_count = 0
                for version in versions:
                    try:
                        has_changed = await monitor.check_for_changes(db, version)
                        if has_changed:
                            changed_count += 1
                            # Re-fetch and re-parse
                            await process_changed_document(
                                db, version, fetcher, parser, embedding_service
                            )
                    except Exception as e:
                        logger.error(f"Error checking version {version.id}: {e}")
                
                if changed_count > 0:
                    db.commit()
                    logger.info(f"Processed {changed_count} changed documents")
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error in reconciliation cycle: {e}", exc_info=True)


async def process_discovered_document(db, doc_info, fetcher, parser, embedding_service, kafka_producer):
    """Process a newly discovered document."""
    from models import DocumentVersion, Document, Case, DocumentSection, EmbeddingChunk
    import uuid
    import hashlib
    
    url = doc_info['url']
    doc_id = doc_info.get('doc_id') or str(uuid.uuid4())
    
    active_document_processing.labels(stage='fetch').inc()
    fetch_start = time.time()
    
    # Fetch document
    try:
        fetch_result = await fetcher.fetch_document(url, doc_id)
        fetch_duration = time.time() - fetch_start
        document_processing_duration.labels(stage='fetch').observe(fetch_duration)
        active_document_processing.labels(stage='fetch').dec()
        
        if not fetch_result:
            logger.warning(f"Failed to fetch document from {url}")
            documents_fetched.labels(status='failed').inc()
            kafka_producer.publish_failed(
                doc_id=doc_id,
                stage='fetch',
                error='Failed to fetch document',
                error_details={'url': url}
            )
            return
        
        documents_fetched.labels(status='success').inc()
        
        # Calculate SHA256 hash
        sha256 = hashlib.sha256(fetch_result.get('content', b'')).hexdigest()
        
        # Publish fetched event to Kafka
        kafka_producer.publish_fetched(
            doc_id=doc_id,
            storage_path=fetch_result.get('storage_path', ''),
            sha256=sha256
        )
    except Exception as e:
        logger.error(f"Error fetching document {doc_id}: {e}", exc_info=True)
        kafka_producer.publish_failed(
            doc_id=doc_id,
            stage='fetch',
            error=str(e),
            error_details={'url': url}
        )
        raise
    
    # Parse document
    active_document_processing.labels(stage='parse').inc()
    parse_start = time.time()
    
    try:
        parsed_data = parser.parse(
            fetch_result['content'],
            fetch_result['content_type'],
            url
        )
        parse_duration = time.time() - parse_start
        document_processing_duration.labels(stage='parse').observe(parse_duration)
        active_document_processing.labels(stage='parse').dec()
        documents_parsed.labels(status='success').inc()
    except Exception as e:
        parse_duration = time.time() - parse_start
        document_processing_duration.labels(stage='parse').observe(parse_duration)
        active_document_processing.labels(stage='parse').dec()
        documents_parsed.labels(status='failed').inc()
        logger.error(f"Error parsing document {doc_id}: {e}", exc_info=True)
        kafka_producer.publish_failed(
            doc_id=doc_id,
            stage='parse',
            error=str(e),
            error_details={'url': url, 'content_type': fetch_result.get('content_type')}
        )
        raise
    
    # Create or get case (simplified - would need proper case matching)
    case = db.query(Case).filter(Case.registry_number == parsed_data.get('case_number')).first()
    if not case:
        # Create new case (simplified)
        case = Case(
            id=uuid.uuid4(),
            registry_number=parsed_data.get('case_number') or doc_id,
            category=None,
            status='active'
        )
        db.add(case)
        db.flush()
    
    # Create document
    document = Document(
        id=uuid.UUID(doc_id),
        case_id=case.id,
        type='decision'
    )
    db.add(document)
    db.flush()
    
    # Create document version
    version = DocumentVersion(
        id=uuid.uuid4(),
        document_id=document.id,
        version_number=1,
        published_at=None,  # Would parse from document
        source_url=url,
        source_hash=fetch_result.get('hash', ''),
        raw_storage_path=fetch_result.get('storage_path', ''),
        parsed_json=parsed_data
    )
    db.add(version)
    document.current_version_id = version.id
    db.flush()
    
    # Extract entities and law references from parsed data
    entities = {
        'court': parsed_data.get('court'),
        'judge': parsed_data.get('judge'),
        'parties': parsed_data.get('parties', {}),
        'date': parsed_data.get('date')
    }
    law_refs = parsed_data.get('law_references', [])
    
    # Publish parsed event to Kafka
    try:
        kafka_producer.publish_parsed(
            doc_id=doc_id,
            version_id=str(version.id),
            entities=entities,
            law_refs=law_refs
        )
    except Exception as e:
        logger.warning(f"Failed to publish parsed event: {e}")
    
    # Create document sections
    for idx, section_data in enumerate(parsed_data.get('text_blocks', [])):
        section = DocumentSection(
            id=uuid.uuid4(),
            document_version_id=version.id,
            section_type=section_data.get('type', 'TEXT'),
            order_index=idx,
            text=section_data.get('text', '')
        )
        db.add(section)
        db.flush()
        
        # Generate embeddings for section
        section_text = section.text
        if section_text:
            chunks = embedding_service.chunk_text(section_text)
            embedding_start = time.time()
            embeddings = await embedding_service.generate_embeddings(chunks)
            embedding_duration = time.time() - embedding_start
            embedding_generation_duration.observe(embedding_duration)
            embeddings_generated.inc(len(embeddings))
            
            for chunk_idx, (chunk_text, embedding) in enumerate(zip(chunks, embeddings)):
                chunk = EmbeddingChunk(
                    id=uuid.uuid4(),
                    section_id=section.id,
                    chunk_index=chunk_idx,
                    text=chunk_text,
                    embedding_vector=embedding,
                    token_count=embedding_service.count_tokens(chunk_text)
                )
                db.add(chunk)
    
    logger.info(f"Processed document {doc_id}")


async def process_changed_document(db, old_version, fetcher, parser, embedding_service):
    """Process a changed document (create new version)."""
    from models import DocumentVersion, Document, DocumentSection, EmbeddingChunk
    import uuid
    import hashlib
    
    kafka_producer = get_producer()
    doc_id = str(old_version.document_id)
    
    # Fetch new version
    try:
        fetch_result = await fetcher.fetch_document(old_version.source_url, doc_id)
        if not fetch_result:
            kafka_producer.publish_failed(
                doc_id=doc_id,
                stage='fetch',
                error='Failed to fetch changed document',
                error_details={'url': old_version.source_url}
            )
            return
        
        # Calculate SHA256 hash
        sha256 = hashlib.sha256(fetch_result.get('content', b'')).hexdigest()
        
        # Publish fetched event
        kafka_producer.publish_fetched(
            doc_id=doc_id,
            storage_path=fetch_result.get('storage_path', ''),
            sha256=sha256
        )
    except Exception as e:
        logger.error(f"Error fetching changed document {doc_id}: {e}", exc_info=True)
        kafka_producer.publish_failed(
            doc_id=doc_id,
            stage='fetch',
            error=str(e),
            error_details={'url': old_version.source_url}
        )
        raise
    
    # Parse new version
    try:
        parsed_data = parser.parse(
            fetch_result['content'],
            fetch_result.get('content_type', 'text/html'),
            old_version.source_url
        )
    except Exception as e:
        logger.error(f"Error parsing changed document {doc_id}: {e}", exc_info=True)
        kafka_producer.publish_failed(
            doc_id=doc_id,
            stage='parse',
            error=str(e),
            error_details={'url': old_version.source_url}
        )
        raise
    
    # Get document
    document = db.query(Document).filter(Document.id == old_version.document_id).first()
    if not document:
        return
    
    # Get next version number
    max_version = db.query(DocumentVersion).filter(
        DocumentVersion.document_id == document.id
    ).order_by(DocumentVersion.version_number.desc()).first()
    
    next_version_num = (max_version.version_number if max_version else 0) + 1
    
    # Create new version
    new_version = DocumentVersion(
        id=uuid.uuid4(),
        document_id=document.id,
        version_number=next_version_num,
        published_at=old_version.published_at,
        source_url=old_version.source_url,
        source_hash=fetch_result.get('hash', ''),
        raw_storage_path=fetch_result.get('storage_path', ''),
        parsed_json=parsed_data
    )
    db.add(new_version)
    document.current_version_id = new_version.id
    db.flush()
    
    # Extract entities and law references
    entities = {
        'court': parsed_data.get('court'),
        'judge': parsed_data.get('judge'),
        'parties': parsed_data.get('parties', {}),
        'date': parsed_data.get('date')
    }
    law_refs = parsed_data.get('law_references', [])
    
    # Publish parsed event
    try:
        kafka_producer.publish_parsed(
            doc_id=doc_id,
            version_id=str(new_version.id),
            entities=entities,
            law_refs=law_refs
        )
    except Exception as e:
        logger.warning(f"Failed to publish parsed event: {e}")
    
    # Create sections and embeddings (same as in process_discovered_document)
    for idx, section_data in enumerate(parsed_data.get('text_blocks', [])):
        section = DocumentSection(
            id=uuid.uuid4(),
            document_version_id=new_version.id,
            section_type=section_data.get('type', 'TEXT'),
            order_index=idx,
            text=section_data.get('text', '')
        )
        db.add(section)
        db.flush()
        
        # Generate embeddings
        section_text = section.text
        if section_text:
            chunks = embedding_service.chunk_text(section_text)
            embeddings = await embedding_service.generate_embeddings(chunks)
            
            for chunk_idx, (chunk_text, embedding) in enumerate(zip(chunks, embeddings)):
                chunk = EmbeddingChunk(
                    id=uuid.uuid4(),
                    section_id=section.id,
                    chunk_index=chunk_idx,
                    text=chunk_text,
                    embedding_vector=embedding,
                    token_count=embedding_service.count_tokens(chunk_text)
                )
                db.add(chunk)
    
    logger.info(f"Created new version {next_version_num} for document {document.id}")


def run_background_worker():
    """Run background worker in separate process."""
    try:
        asyncio.run(run_background_services())
    except KeyboardInterrupt:
        logger.info("Background worker interrupted")
    except Exception as e:
        logger.error(f"Background worker error: {e}")


def main():
    """Main entry point."""
    logger.info("Starting Court Registry MCP Server...")
    
    # Initialize database
    init_database()
    
    # Start MinIO server if using MinIO storage
    minio_process = None
    if settings.storage_type == "minio":
        minio_process = Process(target=run_minio_server, daemon=True)
        minio_process.start()
        logger.info("MinIO server started")
        # Wait a bit for MinIO to start
        import time
        time.sleep(3)
    
    # Start API server in separate process
    api_process = Process(target=run_api_server, daemon=True)
    api_process.start()
    logger.info(f"API server started on {settings.mcp_server_host}:{settings.mcp_server_port}")
    
    # Start background services
    background_process = Process(target=run_background_worker, daemon=True)
    background_process.start()
    logger.info("Background services started")
    
    # Handle shutdown
    def signal_handler(sig, frame):
        logger.info("Shutting down...")
        if minio_process:
            minio_process.terminate()
        api_process.terminate()
        background_process.terminate()
        if minio_process:
            minio_process.join()
        api_process.join()
        background_process.join()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Keep main process alive
    try:
        if minio_process:
            minio_process.join()
        api_process.join()
        background_process.join()
    except KeyboardInterrupt:
        signal_handler(None, None)


if __name__ == "__main__":
    main()
