"""Change Monitor service - discovers new and modified court documents."""
import asyncio
import hashlib
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
import httpx
from bs4 import BeautifulSoup
from config import settings
from models import DocumentVersion, Case, Document
from services.storage import StorageService

logger = logging.getLogger(__name__)


class ChangeMonitor:
    """Monitors court registry for new and changed documents."""
    
    def __init__(self):
        self.base_url = settings.court_registry_base_url
        self.search_endpoint = settings.court_registry_search_endpoint
        self.rss_endpoint = settings.court_registry_rss_endpoint
        self.storage = StorageService()
        self.http_client = httpx.AsyncClient(
            timeout=settings.fetcher_timeout,
            follow_redirects=True
        )
    
    async def close(self):
        """Close HTTP client."""
        await self.http_client.aclose()
    
    async def discover_documents(self, db: Session) -> List[Dict]:
        """
        Discover new and modified documents from court registry.
        
        Returns:
            List of discovered documents with metadata
        """
        discovered = []
        
        try:
            # Strategy 1: Check RSS feed if available
            rss_docs = await self._discover_from_rss(db)
            discovered.extend(rss_docs)
            
            # Strategy 2: Check search results (recent cases)
            search_docs = await self._discover_from_search(db)
            discovered.extend(search_docs)
            
            logger.info(f"Discovered {len(discovered)} new/modified documents")
            return discovered
            
        except Exception as e:
            logger.error(f"Error in discovery: {e}", exc_info=True)
            return discovered
    
    async def _discover_from_rss(self, db: Session) -> List[Dict]:
        """Discover documents from RSS feed."""
        discovered = []
        
        try:
            rss_url = f"{self.base_url}{self.rss_endpoint}"
            response = await self.http_client.get(rss_url)
            response.raise_for_status()
            
            # Parse RSS feed
            soup = BeautifulSoup(response.text, 'xml')
            items = soup.find_all('item')
            
            for item in items[:100]:  # Limit to recent 100
                link = item.find('link')
                if not link:
                    continue
                
                url = link.text.strip()
                doc_id = self._extract_doc_id_from_url(url)
                
                if not doc_id:
                    continue
                
                # Check if we already have this document
                existing = db.query(DocumentVersion).filter(
                    DocumentVersion.source_url == url
                ).first()
                
                if not existing:
                    discovered.append({
                        "doc_id": doc_id,
                        "url": url,
                        "discovered_at": datetime.utcnow(),
                        "hash_hint": None
                    })
                else:
                    # Check if document might have changed
                    # In production, would fetch and compare hash
                    pass
            
        except Exception as e:
            logger.warning(f"RSS discovery failed: {e}")
        
        return discovered
    
    async def _discover_from_search(self, db: Session, date_from: Optional[str] = None, date_to: Optional[str] = None) -> List[Dict]:
        """Discover documents from search results."""
        discovered = []
        
        try:
            # Search for cases in date range
            search_url = f"{self.base_url}{self.search_endpoint}"
            if not date_from:
                date_from = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
            if not date_to:
                date_to = datetime.utcnow().strftime("%Y-%m-%d")
            
            params = {
                "date_from": date_from,
                "date_to": date_to
            }
            
            logger.info(f"[SEARCH_ENTER] Starting search: url={search_url}, params={params}")
            logger.debug(f"[SEARCH_DATA] Search parameters: date_from={date_from}, date_to={date_to}")
            
            response = await self.http_client.get(search_url, params=params)
            response.raise_for_status()
            
            logger.info(f"[SEARCH_HTTP] Response received: status={response.status_code}, size={len(response.text)} bytes")
            logger.debug(f"[SEARCH_HTTP] Response headers: {dict(response.headers)}")
            
            # Parse search results
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Try to find pagination info
            total_cases = None
            total_pages = None
            current_page = None
            
            # Look for common pagination patterns
            pagination_text = soup.get_text()
            if 'Документів у системі:' in pagination_text or 'Документів:' in pagination_text:
                logger.debug(f"[SEARCH_DATA] Found pagination text in response")
            
            # Try to find result count
            result_count_elements = soup.find_all(string=lambda text: text and ('Документів' in text or 'записів' in text or 'результатів' in text))
            if result_count_elements:
                logger.info(f"[SEARCH_DATA] Found result count elements: {len(result_count_elements)}")
                for elem in result_count_elements:
                    logger.debug(f"[SEARCH_DATA] Result count text: {elem.strip()}")
            
            # Find all links that might be documents
            links = soup.find_all('a', href=True)
            logger.info(f"[SEARCH_DATA] Found {len(links)} total links in search results")
            
            document_links = []
            for link in links:
                href = link.get('href', '')
                if '/Document/' in href or '/Case/' in href:
                    document_links.append((href, link.get_text(strip=True)))
            
            logger.info(f"[SEARCH_DATA] Found {len(document_links)} document/case links")
            
            # Process document links
            processed = 0
            skipped = 0
            for href, link_text in document_links[:100]:  # Limit to 100 per page
                full_url = self._make_absolute_url(href)
                doc_id = self._extract_doc_id_from_url(full_url)
                
                if not doc_id:
                    logger.debug(f"[SEARCH_DATA] Could not extract doc_id from URL: {href}")
                    continue
                
                logger.debug(f"[SEARCH_DATA] Processing document: doc_id={doc_id}, url={full_url}, link_text={link_text[:50]}")
                
                # Check if new
                existing = db.query(DocumentVersion).filter(
                    DocumentVersion.source_url == full_url
                ).first()
                
                if not existing:
                    discovered.append({
                        "doc_id": doc_id,
                        "url": full_url,
                        "discovered_at": datetime.utcnow(),
                        "hash_hint": None
                    })
                    processed += 1
                    logger.debug(f"[SEARCH_DATA] New document discovered: doc_id={doc_id}")
                else:
                    skipped += 1
                    logger.debug(f"[SEARCH_DATA] Document already exists: doc_id={doc_id}")
            
            logger.info(f"[SEARCH_EXIT] Search completed: discovered={len(discovered)}, processed={processed}, skipped={skipped}, total_links={len(document_links)}")
            
        except Exception as e:
            logger.error(f"[SEARCH_ERROR] Search discovery failed: {e}", exc_info=True)
        
        return discovered
    
    def _extract_doc_id_from_url(self, url: str) -> Optional[str]:
        """Extract document ID from URL."""
        # Placeholder - actual implementation depends on URL structure
        # Example: https://reyestr.court.gov.ua/Document/12345678
        parts = url.split('/')
        if 'Document' in parts:
            idx = parts.index('Document')
            if idx + 1 < len(parts):
                return parts[idx + 1]
        return None
    
    def _make_absolute_url(self, href: str) -> str:
        """Convert relative URL to absolute."""
        if href.startswith('http'):
            return href
        return f"{self.base_url}{href}"
    
    async def check_for_changes(self, db: Session, doc_version: DocumentVersion) -> bool:
        """
        Check if a document has changed by comparing hashes.
        
        Returns:
            True if document has changed
        """
        try:
            # Fetch current version
            response = await self.http_client.get(doc_version.source_url)
            response.raise_for_status()
            
            current_hash = self.storage.calculate_hash(response.content)
            
            # Compare with stored hash
            if doc_version.source_hash != current_hash:
                logger.info(f"Document {doc_version.id} has changed (hash mismatch)")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking changes for {doc_version.id}: {e}")
            return False
