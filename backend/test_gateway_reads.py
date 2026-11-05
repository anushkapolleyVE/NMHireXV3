"""Test script for WhatsApp Integration Gateway Read APIs.

Calls:
1. fetch_schedules (API 1) for date range 2026-11-01 to 2026-11-05
2. fetch_interview_results (API 2) for date range 2026-11-01 to 2026-11-05
Prints totalCount, total pages, and request IDs.
"""

import os
import sys
from pathlib import Path

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Attempt to load .env if python-dotenv is installed
try:
    from dotenv import load_dotenv
    load_dotenv(backend_dir / ".env")
except ImportError:
    pass

from app.gateway_client import (
    GatewayAuthError,
    GatewayForbiddenError,
    GatewayRateLimitError,
    GatewayServerError,
    GatewayValidationError,
    GatewayError,
)
from app.gateway_service import fetch_interview_results, fetch_schedules, add_candidate


def run_tests():
    start_date = "2026-11-01"
    end_date = "2026-11-05"

    gateway_url = os.getenv("NMHIREX_GATEWAY_URL", "")
    api_key = os.getenv("NMHIREX_API_KEY", "")

    print("=" * 65)
    print(" WhatsApp Integration Gateway - Read APIs Test")
    print("=" * 65)
    print(f"Gateway URL: {gateway_url or '[NOT CONFIGURED]'}")
    print(f"API Key:     {'*' * 8 + api_key[-6:] if len(api_key) > 6 else '[NOT CONFIGURED]'}")
    print(f"Date Range:  {start_date} to {end_date}")
    print("-" * 65)

    if not gateway_url or not api_key:
        print("[!] ERROR: NMHIREX_GATEWAY_URL or NMHIREX_API_KEY is not set.")
        print("    Please set them in backend/.env before running this test script.")
        print("=" * 65)
        return

    # ---------------------------------------------------------
    # TEST 1: Scheduled Interviews (API 1)
    # ---------------------------------------------------------
    print("\n[1/2] Fetching Scheduled Interviews (API 1)...")
    try:
        schedules_res = fetch_schedules({
            "startDate": start_date,
            "endDate": end_date,
            "dateType": "interview_date",
            "pageSize": 50,
        })
        schedules_data = schedules_res.get("data", [])
        total_count_1 = schedules_res.get("totalCount", len(schedules_data))
        total_pages_1 = schedules_res.get("totalPages", 1)
        req_id_1 = schedules_res.get("requestId", "N/A")

        print("  ✓ Success!")
        print(f"  - Request ID:   {req_id_1}")
        print(f"  - Total Count:  {total_count_1}")
        print(f"  - Total Pages:  {total_pages_1}")
        print(f"  - Rows Fetched: {len(schedules_data)}")
        if schedules_data:
            sample = schedules_data[0]
            print(f"  - Sample candidate: {sample.get('user_name')} ({sample.get('email')}) "
                  f"on {sample.get('interview_date')} {sample.get('interview_time')}")
    except GatewayError as exc:
        print(f"  ✗ Failed (HTTP {exc.status_code}): {exc.message}")
        print(f"    Request ID: {exc.request_id}")
    except Exception as exc:
        print(f"  ✗ Unexpected Error: {exc}")

    # ---------------------------------------------------------
    # TEST 2: Interview Results (API 2)
    # ---------------------------------------------------------
    print("\n[2/2] Fetching Interview Results (API 2)...")
    try:
        results_res = fetch_interview_results({
            "startDate": start_date,
            "endDate": end_date,
            "pageSize": 50,
        })
        results_data = results_res.get("data", [])
        total_count_2 = results_res.get("totalCount", len(results_data))
        total_pages_2 = results_res.get("totalPages", 1)
        req_id_2 = results_res.get("requestId", "N/A")

        print("  ✓ Success!")
        print(f"  - Request ID:   {req_id_2}")
        print(f"  - Total Count:  {total_count_2}")
        print(f"  - Total Pages:  {total_pages_2}")
        print(f"  - Rows Fetched: {len(results_data)}")
        if results_data:
            sample = results_data[0]
            print(f"  - Sample result: {sample.get('candidate_name')} - "
                  f"Result: {sample.get('result')}, Score: {sample.get('score')} "
                  f"({sample.get('test_type_name')})")
    except GatewayError as exc:
        print(f"  ✗ Failed (HTTP {exc.status_code}): {exc.message}")
        print(f"    Request ID: {exc.request_id}")
    except Exception as exc:
        print(f"  ✗ Unexpected Error: {exc}")

    print("\n" + "=" * 65)
    print(" Test execution finished.")
    print("=" * 65)


if __name__ == "__main__":
    run_tests()

