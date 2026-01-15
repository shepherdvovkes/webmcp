#!/usr/bin/env python3
"""
Script to trigger the backend to fetch all cases registered from a specific date 
from https://reyestr.court.gov.ua/
"""
import requests
import json
import sys
import os
from datetime import datetime
from typing import Optional, Dict, Any


def trigger_fetch(
    gate_server_url: str,
    date_from: str = "2026-01-01",
    date_to: Optional[str] = None,
    force: bool = False,
    output_file: Optional[str] = None
) -> Dict[str, Any]:
    """
    Trigger the backend to fetch cases from the registry.
    
    Args:
        gate_server_url: Base URL of the gate server (e.g., "https://api.example.com")
        date_from: Start date in YYYY-MM-DD format
        date_to: End date in YYYY-MM-DD format (optional)
        force: Force re-fetch even if documents already exist
        output_file: Optional file path to save the results as JSON
    
    Returns:
        Dictionary containing the API response
    """
    # Construct the API endpoint URL
    api_url = f"{gate_server_url.rstrip('/')}/api/trigger_fetch"
    
    # Prepare the request payload
    payload = {
        "date_from": date_from,
        "force": force
    }
    
    if date_to:
        payload["date_to"] = date_to
    
    # Make the API request
    print(f"Triggering fetch from registry: https://reyestr.court.gov.ua/")
    print(f"Date range: {date_from} to {date_to or 'today'}")
    print(f"API URL: {api_url}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    print()
    
    try:
        response = requests.post(
            api_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=300  # 5 minutes timeout for discovery
        )
        
        # Check if request was successful
        response.raise_for_status()
        
        # Parse the response
        result = response.json()
        
        # Print summary
        print("=" * 60)
        print("FETCH TRIGGER RESULTS")
        print("=" * 60)
        print(f"Status: {result.get('status', 'unknown')}")
        print(f"Discovered documents: {result.get('discovered', 0)}")
        print(f"Queued for processing: {result.get('queued', 0)}")
        print(f"Skipped (already exist): {result.get('skipped', 0)}")
        print(f"Failed: {result.get('failed', 0)}")
        print()
        
        if result.get('message'):
            print(f"Message: {result.get('message')}")
        
        print()
        print("Note: Documents are queued for background processing.")
        print("The fetcher will download them using 5 concurrent threads.")
        print("Check the logs or metrics endpoint for processing status.")
        
        # Save to file if requested
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False, default=str)
            print(f"\nResults saved to: {output_file}")
        
        return result
        
    except requests.exceptions.RequestException as e:
        print(f"Error making request: {e}", file=sys.stderr)
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response status: {e.response.status_code}", file=sys.stderr)
            try:
                error_detail = e.response.json()
                print(f"Response body: {json.dumps(error_detail, indent=2)}", file=sys.stderr)
            except:
                print(f"Response text: {e.response.text}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON response: {e}", file=sys.stderr)
        print(f"Response text: {response.text}", file=sys.stderr)
        sys.exit(1)


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Trigger backend to fetch cases from https://reyestr.court.gov.ua/ for a specific date range"
    )
    parser.add_argument(
        "--gate-server",
        default=os.getenv("GATE_SERVER_URL", "http://localhost:8000"),
        help="Base URL of the gate server (default: from GATE_SERVER_URL env var or http://localhost:8000)"
    )
    parser.add_argument(
        "--date-from",
        default="2026-01-01",
        help="Start date in YYYY-MM-DD format (default: 2026-01-01)"
    )
    parser.add_argument(
        "--date-to",
        default=None,
        help="End date in YYYY-MM-DD format (optional, defaults to today)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-fetch even if documents already exist"
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Output file path to save results as JSON (optional)"
    )
    
    args = parser.parse_args()
    
    # Validate date format
    try:
        datetime.strptime(args.date_from, "%Y-%m-%d")
    except ValueError:
        print(f"Error: Invalid date format for --date-from: {args.date_from}", file=sys.stderr)
        print("Expected format: YYYY-MM-DD", file=sys.stderr)
        sys.exit(1)
    
    if args.date_to:
        try:
            datetime.strptime(args.date_to, "%Y-%m-%d")
        except ValueError:
            print(f"Error: Invalid date format for --date-to: {args.date_to}", file=sys.stderr)
            print("Expected format: YYYY-MM-DD", file=sys.stderr)
            sys.exit(1)
    
    # Trigger fetch
    result = trigger_fetch(
        gate_server_url=args.gate_server,
        date_from=args.date_from,
        date_to=args.date_to,
        force=args.force,
        output_file=args.output
    )
    
    return result


if __name__ == "__main__":
    main()
