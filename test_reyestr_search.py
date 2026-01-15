#!/usr/bin/env python3
"""Test script to check reyestr.court.gov.ua search and count cases/pages."""
import asyncio
import logging
from datetime import datetime
from services.change_monitor import ChangeMonitor
from bs4 import BeautifulSoup
import httpx

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def test_reyestr_search():
    """Test search in reyestr.court.gov.ua and count cases/pages."""
    print("=" * 70)
    print("TESTING REYESTR.COURT.GOV.UA SEARCH")
    print("=" * 70)
    print()
    
    date_from = "2026-01-01"
    date_to = datetime.utcnow().strftime("%Y-%m-%d")
    
    print(f"Search date range: {date_from} to {date_to}")
    print()
    
    monitor = ChangeMonitor()
    
    try:
        search_url = f"{monitor.base_url}{monitor.search_endpoint}"
        params = {
            "date_from": date_from,
            "date_to": date_to
        }
        
        print(f"[SEARCH] URL: {search_url}")
        print(f"[SEARCH] Parameters: {params}")
        print()
        
        logger.info(f"[TEST_SEARCH] Making search request: url={search_url}, params={params}")
        
        # The search form requires POST with form data
        # First, get the search page to get any required tokens/fields
        initial_response = await monitor.http_client.get(search_url)
        initial_response.raise_for_status()
        
        logger.info(f"[TEST_SEARCH] Got initial page: status={initial_response.status_code}, size={len(initial_response.text)} bytes")
        
        # Parse form to get all required fields
        soup_initial = BeautifulSoup(initial_response.text, 'html.parser')
        form = soup_initial.find('form')
        
        if form:
            logger.info(f"[TEST_SEARCH] Found form: action={form.get('action')}, method={form.get('method')}")
            
            # Build form data
            form_data = {}
            
            # Add date fields
            form_data['RegDateBegin'] = date_from
            form_data['RegDateEnd'] = date_to
            form_data['ImportDateBegin'] = ''
            form_data['ImportDateEnd'] = ''
            
            # Get all hidden inputs
            for input_field in soup_initial.find_all('input', type='hidden'):
                name = input_field.get('name')
                value = input_field.get('value', '')
                if name:
                    form_data[name] = value
                    logger.debug(f"[TEST_SEARCH] Added hidden field: {name}={value[:50]}")
            
            logger.info(f"[TEST_SEARCH] Submitting POST with {len(form_data)} form fields")
            logger.debug(f"[TEST_SEARCH] Form data keys: {list(form_data.keys())}")
            
            # Submit POST request
            response = await monitor.http_client.post(search_url, data=form_data, follow_redirects=True)
            response.raise_for_status()
        else:
            # Fallback to GET if no form found
            logger.warning(f"[TEST_SEARCH] No form found, using GET as fallback")
            response = await monitor.http_client.get(search_url, params=params)
            response.raise_for_status()
        
        print(f"[SEARCH] Response status: {response.status_code}")
        print(f"[SEARCH] Response size: {len(response.text)} bytes")
        print()
        
        # Parse HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Try to find total document count
        print("=" * 70)
        print("ANALYZING SEARCH RESULTS")
        print("=" * 70)
        print()
        
        # Look for document count text
        page_text = soup.get_text()
        
        # Common patterns in Ukrainian court registry
        count_patterns = [
            'Документів у системі:',
            'Документів:',
            'Знайдено документів:',
            'Всього документів:',
            'записів',
            'результатів'
        ]
        
        found_count = None
        for pattern in count_patterns:
            if pattern in page_text:
                # Try to extract number
                idx = page_text.find(pattern)
                snippet = page_text[idx:idx+100]
                print(f"[FOUND] Pattern '{pattern}' found in page text")
                print(f"[SNIPPET] {snippet[:80]}...")
                
                # Try to extract number
                import re
                numbers = re.findall(r'\d+', snippet.replace(' ', '').replace(',', ''))
                if numbers:
                    found_count = numbers[0]
                    print(f"[COUNT] Extracted number: {found_count}")
                print()
        
        # Count document links
        all_links = soup.find_all('a', href=True)
        document_links = [link for link in all_links if '/Document/' in link.get('href', '') or '/Case/' in link.get('href', '')]
        
        print(f"[LINKS] Total links on page: {len(all_links)}")
        print(f"[LINKS] Document/Case links: {len(document_links)}")
        print()
        
        # Try to find pagination
        pagination_links = soup.find_all('a', href=True, string=lambda text: text and any(char.isdigit() for char in str(text)))
        page_numbers = []
        for link in pagination_links:
            href = link.get('href', '')
            text = link.get_text(strip=True)
            if text.isdigit() or 'page' in href.lower() or 'сторінк' in text.lower():
                page_numbers.append((text, href))
        
        print(f"[PAGINATION] Found {len(page_numbers)} potential pagination links")
        if page_numbers:
            print(f"[PAGINATION] Sample: {page_numbers[:5]}")
        print()
        
        # Count unique document URLs
        unique_docs = set()
        for link in document_links:
            href = link.get('href', '')
            if '/Document/' in href:
                doc_id = monitor._extract_doc_id_from_url(monitor._make_absolute_url(href))
                if doc_id:
                    unique_docs.add(doc_id)
        
        print("=" * 70)
        print("SEARCH RESULTS SUMMARY")
        print("=" * 70)
        print(f"Date range: {date_from} to {date_to}")
        print(f"Total document links found on page: {len(document_links)}")
        print(f"Unique document IDs: {len(unique_docs)}")
        if found_count:
            print(f"Total documents in system (from page text): {found_count}")
        print(f"Pagination links found: {len(page_numbers)}")
        print()
        
        # Save HTML for inspection
        print("[DEBUG] Saving search results HTML for inspection...")
        with open('/tmp/reyestr_search_result.html', 'w', encoding='utf-8') as f:
            f.write(response.text)
        print("[DEBUG] Saved to /tmp/reyestr_search_result.html")
        print()
        
        # Show sample document links
        if document_links:
            print("=" * 70)
            print("SAMPLE DOCUMENT LINKS (first 10)")
            print("=" * 70)
            for i, link in enumerate(document_links[:10], 1):
                href = link.get('href', '')
                text = link.get_text(strip=True)[:60]
                print(f"{i}. {text}")
                print(f"   URL: {monitor._make_absolute_url(href)}")
            print()
        
    except Exception as e:
        logger.error(f"[TEST_SEARCH_ERROR] Error: {e}", exc_info=True)
        print(f"ERROR: {e}")
    finally:
        await monitor.close()
    
    print("=" * 70)
    print("TEST COMPLETED")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(test_reyestr_search())
