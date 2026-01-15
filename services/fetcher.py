"""Fetcher Pool service - downloads documents with retry logic."""
import asyncio
import logging
from typing import Optional, Dict
import httpx
from datetime import datetime
from config import settings
from services.storage import StorageService

logger = logging.getLogger(__name__)


class FetcherPool:
    """Pool of workers for fetching documents."""
    
    def __init__(self):
        logger.info(f"[FETCHER_INIT] Initializing FetcherPool with {settings.fetcher_workers} workers")
        self.workers = settings.fetcher_workers
        self.max_retries = settings.fetcher_max_retries
        self.timeout = settings.fetcher_timeout
        self.storage = StorageService()
        self.semaphore = asyncio.Semaphore(self.workers)
        self.http_client = httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            limits=httpx.Limits(max_connections=self.workers * 2)
        )
        logger.info(f"[FETCHER_INIT] FetcherPool initialized: workers={self.workers}, max_retries={self.max_retries}, timeout={self.timeout}s")
    
    async def close(self):
        """Close HTTP client."""
        logger.info("[FETCHER_CLOSE] Closing FetcherPool HTTP client")
        await self.http_client.aclose()
        logger.info("[FETCHER_CLOSE] FetcherPool HTTP client closed")
    
    async def fetch_document(self, url: str, doc_id: str) -> Optional[Dict]:
        """
        Fetch a document with retry logic.
        
        Args:
            url: Document URL
            doc_id: Document UUID
            
        Returns:
            Dict with content, hash, and storage path, or None if failed
        """
        logger.info(f"[FETCHER_ENTER] fetch_document called: doc_id={doc_id}, url={url}")
        logger.debug(f"[FETCHER_DATA] Input data: doc_id={doc_id}, url={url}, workers={self.workers}, max_retries={self.max_retries}")
        
        # Log semaphore acquisition
        logger.debug(f"[FETCHER_SEMAPHORE] Waiting for semaphore slot (available workers: {self.workers})")
        async with self.semaphore:
            logger.info(f"[FETCHER_SEMAPHORE] Semaphore acquired for doc_id={doc_id}, url={url}")
            
            for attempt in range(self.max_retries):
                try:
                    logger.info(f"[FETCHER_ATTEMPT] Fetching doc_id={doc_id}, url={url}, attempt={attempt + 1}/{self.max_retries}")
                    
                    # Log HTTP request
                    logger.debug(f"[FETCHER_HTTP] Sending GET request to url={url}, timeout={self.timeout}s")
                    response = await self.http_client.get(url)
                    logger.debug(f"[FETCHER_HTTP] Response received: status={response.status_code}, headers={dict(response.headers)}")
                    response.raise_for_status()
                    
                    # Determine file extension
                    content_type = response.headers.get('content-type', '')
                    if 'pdf' in content_type.lower():
                        ext = 'pdf'
                    else:
                        ext = 'html'
                    
                    content = response.content
                    content_size = len(content)
                    logger.info(f"[FETCHER_DATA] Content received: doc_id={doc_id}, size={content_size} bytes, content_type={content_type}, extension={ext}")
                    
                    # Calculate hash
                    logger.debug(f"[FETCHER_DATA] Calculating hash for doc_id={doc_id}, size={content_size} bytes")
                    content_hash = self.storage.calculate_hash(content)
                    logger.info(f"[FETCHER_DATA] Hash calculated: doc_id={doc_id}, hash={content_hash}, size={content_size} bytes")
                    
                    # Save to storage
                    logger.info(f"[FETCHER_STORAGE] Saving document: doc_id={doc_id}, extension={ext}, size={content_size} bytes")
                    storage_path = self.storage.save(doc_id, content, ext)
                    logger.info(f"[FETCHER_STORAGE] Document saved: doc_id={doc_id}, storage_path={storage_path}, size={content_size} bytes")
                    
                    result = {
                        "content": content,
                        "hash": content_hash,
                        "storage_path": storage_path,
                        "content_type": content_type,
                        "extension": ext,
                        "url": url,
                        "fetched_at": datetime.utcnow()
                    }
                    
                    logger.info(f"[FETCHER_SUCCESS] Successfully fetched doc_id={doc_id}, url={url}, hash={content_hash[:16]}..., size={content_size} bytes, storage_path={storage_path}")
                    logger.debug(f"[FETCHER_DATA] Return data: doc_id={doc_id}, hash={content_hash}, size={content_size}, content_type={content_type}, extension={ext}, storage_path={storage_path}")
                    
                    return result
                    
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 404:
                        logger.warning(f"[FETCHER_ERROR] Document not found: doc_id={doc_id}, url={url}, status=404")
                        logger.info(f"[FETCHER_EXIT] fetch_document returning None (404) for doc_id={doc_id}")
                        return None
                    logger.warning(f"[FETCHER_ERROR] HTTP error: doc_id={doc_id}, url={url}, status={e.response.status_code}, error={e}")
                    
                except httpx.TimeoutException:
                    logger.warning(f"[FETCHER_ERROR] Timeout: doc_id={doc_id}, url={url}, attempt={attempt + 1}, timeout={self.timeout}s")
                    
                except Exception as e:
                    logger.error(f"[FETCHER_ERROR] Exception: doc_id={doc_id}, url={url}, attempt={attempt + 1}, error={e}", exc_info=True)
                
                # Wait before retry (exponential backoff)
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.debug(f"[FETCHER_RETRY] Waiting {wait_time}s before retry for doc_id={doc_id}, attempt={attempt + 1}")
                    await asyncio.sleep(wait_time)
            
            logger.error(f"[FETCHER_FAILED] Failed to fetch after {self.max_retries} attempts: doc_id={doc_id}, url={url}")
            logger.info(f"[FETCHER_EXIT] fetch_document returning None (max retries exceeded) for doc_id={doc_id}")
            return None
    
    async def fetch_batch(self, urls: list[tuple[str, str]]) -> list[Dict]:
        """
        Fetch multiple documents concurrently.
        
        Args:
            urls: List of (url, doc_id) tuples
            
        Returns:
            List of fetch results
        """
        batch_size = len(urls)
        logger.info(f"[FETCHER_BATCH_ENTER] fetch_batch called: batch_size={batch_size}, workers={self.workers}")
        logger.debug(f"[FETCHER_BATCH_DATA] Input URLs: {[f'doc_id={doc_id}, url={url}' for url, doc_id in urls]}")
        
        # Create tasks
        tasks = [self.fetch_document(url, doc_id) for url, doc_id in urls]
        logger.debug(f"[FETCHER_BATCH_DATA] Created {len(tasks)} fetch tasks")
        
        # Execute all tasks concurrently
        logger.info(f"[FETCHER_BATCH_EXEC] Executing {batch_size} fetch tasks concurrently (max {self.workers} workers)")
        results = await asyncio.gather(*tasks, return_exceptions=True)
        logger.info(f"[FETCHER_BATCH_EXEC] All {batch_size} tasks completed")
        
        # Filter out exceptions and None results
        fetched = []
        exceptions = []
        failed = []
        
        for idx, result in enumerate(results):
            url, doc_id = urls[idx]
            if isinstance(result, Exception):
                logger.error(f"[FETCHER_BATCH_ERROR] Exception in batch fetch: doc_id={doc_id}, url={url}, error={result}")
                exceptions.append((doc_id, url, result))
            elif result is not None:
                logger.debug(f"[FETCHER_BATCH_SUCCESS] Successfully fetched: doc_id={doc_id}, url={url}, size={len(result.get('content', []))} bytes")
                fetched.append(result)
            else:
                logger.warning(f"[FETCHER_BATCH_FAILED] Failed to fetch: doc_id={doc_id}, url={url}")
                failed.append((doc_id, url))
        
        logger.info(f"[FETCHER_BATCH_EXIT] Batch fetch completed: total={batch_size}, successful={len(fetched)}, failed={len(failed)}, exceptions={len(exceptions)}")
        logger.debug(f"[FETCHER_BATCH_DATA] Results: successful={len(fetched)}, failed={len(failed)}, exceptions={len(exceptions)}")
        
        return fetched
