#!/usr/bin/env python3
"""
Script to fetch all cases registered from a specific date from the deployed backend on gate server.
"""
import requests
import json
import sys
import os
from datetime import datetime
from typing import Optional, Dict, Any


def fetch_cases(
    gate_server_url: str,
    date_from: str = "2026-01-01",
    date_to: Optional[str] = None,
    limit: int = 1000,
    output_file: Optional[str] = None
) -> Dict[str, Any]:
    """
    Fetch cases from the backend API.
    
    Args:
        gate_server_url: Base URL of the gate server (e.g., "https://api.example.com")
        date_from: Start date in YYYY-MM-DD format
        date_to: End date in YYYY-MM-DD format (optional)
        limit: Maximum number of cases to fetch
        output_file: Optional file path to save the results as JSON
    
    Returns:
        Dictionary containing the API response
    """
    # Construct the API endpoint URL
    api_url = f"{gate_server_url.rstrip('/')}/api/find_cases"
    
    # Prepare the request payload
    payload = {
        "date_from": date_from,
        "limit": limit
    }
    
    if date_to:
        payload["date_to"] = date_to
    
    # Make the API request
    print(f"Fetching cases from {date_from}...")
    print(f"API URL: {api_url}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    try:
        response = requests.post(
            api_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=60
        )
        
        # Check if request was successful
        response.raise_for_status()
        
        # Parse the response
        result = response.json()
        
        # Print summary
        if isinstance(result, dict):
            case_count = len(result.get("cases", []))
            print(f"\nSuccessfully fetched {case_count} cases")
            
            if case_count > 0 and "cases" in result:
                print("\nFirst few cases:")
                for i, case in enumerate(result["cases"][:5], 1):
                    registry_num = case.get("registry_number", "N/A")
                    opened_at = case.get("opened_at", "N/A")
                    status = case.get("status", "N/A")
                    print(f"  {i}. {registry_num} - Opened: {opened_at} - Status: {status}")
        
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
            print(f"Response body: {e.response.text}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON response: {e}", file=sys.stderr)
        print(f"Response text: {response.text}", file=sys.stderr)
        sys.exit(1)


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Fetch all cases registered from a specific date from the gate server backend"
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
        help="End date in YYYY-MM-DD format (optional)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1000,
        help="Maximum number of cases to fetch (default: 1000)"
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
    
    # Fetch cases
    result = fetch_cases(
        gate_server_url=args.gate_server,
        date_from=args.date_from,
        date_to=args.date_to,
        limit=args.limit,
        output_file=args.output
    )
    
    return result


if __name__ == "__main__":
    main()
