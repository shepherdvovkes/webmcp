#!/usr/bin/env python3
"""Test script to demonstrate fetcher logging."""
import asyncio
import logging
import sys

# Configure logging to show all levels
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from services.fetcher import FetcherPool

async def test_fetcher():
    """Test fetcher with logging."""
    print("=" * 60)
    print("TESTING FETCHER WITH LOGGING")
    print("=" * 60)
    print()
    
    # Initialize fetcher (should log initialization)
    fetcher = FetcherPool()
    
    # Test fetching a document (using a simple test URL)
    test_url = "https://httpbin.org/json"
    test_doc_id = "test-doc-123"
    
    print(f"\nTesting fetch with URL: {test_url}")
    print(f"Document ID: {test_doc_id}")
    print()
    
    result = await fetcher.fetch_document(test_url, test_doc_id)
    
    if result:
        print(f"\n✓ Fetch successful!")
        print(f"  Content type: {result.get('content_type')}")
        print(f"  Size: {len(result.get('content', []))} bytes")
        print(f"  Hash: {result.get('hash', '')[:32]}...")
        print(f"  Storage path: {result.get('storage_path', 'N/A')}")
    else:
        print(f"\n✗ Fetch failed")
    
    # Test batch fetch
    print("\n" + "=" * 60)
    print("TESTING BATCH FETCH")
    print("=" * 60)
    print()
    
    batch_urls = [
        ("https://httpbin.org/json", "test-doc-1"),
        ("https://httpbin.org/uuid", "test-doc-2"),
    ]
    
    print(f"Testing batch fetch with {len(batch_urls)} URLs")
    print()
    
    results = await fetcher.fetch_batch(batch_urls)
    
    print(f"\n✓ Batch fetch completed!")
    print(f"  Successful: {len(results)}/{len(batch_urls)}")
    
    # Close fetcher (should log close)
    await fetcher.close()
    
    print("\n" + "=" * 60)
    print("TEST COMPLETED")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_fetcher())
