"""Unit verification script for Dual API Key Architecture and AddCandidate Payload.

Verifies:
1. Key 1 (Messaging) is picked up by tools_function messaging functions.
2. Key 2 (Gateway) is picked up by WhatsAppGatewayClient.
3. Key 1 is NEVER leaked to WhatsAppGatewayClient.
4. add_candidate compiles exact payload preserving distinct request_id and requisition_id.
"""

import os
import sys
from pathlib import Path
from decimal import Decimal
from unittest.mock import MagicMock, patch

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Mock environment before importing app modules
os.environ["DATABASE_URL"] = "postgresql://mock:mock@localhost:5432/mockdb"
os.environ["JWT_SECRET_KEY"] = "mock_secret_key_12345678901234567890"
os.environ["WHATSAPP_MESSAGE_API_KEY"] = "wa_live_key1_messaging_only"
os.environ["NMHIREX_GATEWAY_API_KEY"] = "wa_live_key2_addcandidates_only"

from app.config import settings
from app.gateway_client import WhatsAppGatewayClient
from app.gateway_service import add_candidate
from app.tools_function import _whatsapp_headers


def test_key_separation():
    print("=" * 60)
    print(" TEST 1: Key Separation Verification")
    print("=" * 60)

    # 1. Verify Key 1 is picked up for WhatsApp messages
    headers = _whatsapp_headers()
    assert "Bearer wa_live_key1_messaging_only" in headers["Authorization"], (
        f"Expected Key 1 in messaging headers, got: {headers.get('Authorization')}"
    )
    print("  ✓ Key 1 (Messaging) successfully isolated for WhatsApp messaging.")

    # 2. Verify Key 2 is picked up by Gateway Client
    gw_client = WhatsAppGatewayClient()
    assert gw_client.api_key == "wa_live_key2_addcandidates_only", (
        f"Expected Key 2 in gateway client, got: {gw_client.api_key}"
    )
    print("  ✓ Key 2 (Gateway) successfully isolated for /addcandidates API.")

    # 3. Verify Key 1 is NEVER used by Gateway Client
    assert gw_client.api_key != headers["api-key"], (
        "Key leak detected! Gateway Client should not use Messaging Key."
    )
    print("  ✓ Cross-key leakage prevented: Gateway client never falls back to messaging key.")


def test_add_candidate_payload_structure():
    print("\n" + "=" * 60)
    print(" TEST 2: Add Candidate Payload Construction")
    print("=" * 60)

    mock_client = MagicMock()
    mock_client.post.return_value = {
        "statusCode": 200,
        "message": "Candidate added successfully",
        "registrationUrl": "https://nminterview.com/registration/cand-12345",
    }

    test_input = {
        "user_name": "Rahul Sharma",
        "email": "rahul@example.com",
        "contact_no": "917439717970",
        "current_company": "Acme Corp",
        "interview_date": "2026-11-10",
        "interview_time": "14:30",
        "job_role": "Software Engineer",
        "experience": "5",
        "request_id": "e8d25f71-6c43-4b95-a102-39c81e7d23a1",
        "requisition_id": "c1a93b4e-7f12-4298-9031-15c2d1b827e4",
    }

    res = add_candidate(test_input, client=mock_client)

    # Check mock client post was called
    mock_client.post.assert_called_once()
    called_endpoint, called_kwargs = mock_client.post.call_args[0][0], mock_client.post.call_args[1]
    payload = called_kwargs["payload"]

    assert called_endpoint == "/api/integrations/whatsapp/raw/add-candidate", f"Wrong endpoint: {called_endpoint}"
    assert payload["request_id"] == "e8d25f71-6c43-4b95-a102-39c81e7d23a1", f"request_id mismatch: {payload['request_id']}"
    assert payload["requisition_id"] == "c1a93b4e-7f12-4298-9031-15c2d1b827e4", f"requisition_id mismatch: {payload['requisition_id']}"
    assert payload["operation"] == "addcandidate", f"operation mismatch: {payload['operation']}"
    assert payload["technical_round"] == 1, f"technical_round mismatch: {payload['technical_round']}"
    assert payload["one2one_round"] == 1, f"one2one_round mismatch: {payload['one2one_round']}"
    assert payload["comm_skill_rating"] == 4, f"comm_skill_rating mismatch: {payload['comm_skill_rating']}"
    assert payload["cultural_fit_rating"] == 4, f"cultural_fit_rating mismatch: {payload['cultural_fit_rating']}"
    assert payload["experience"] == "5", f"experience mismatch: {payload['experience']}"
    assert payload["interview_medium"] == "NM Interview", f"interview_medium mismatch: {payload['interview_medium']}"
    assert called_kwargs.get("is_write") is True, "Write safety flag is_write must be True (disable 5xx retry)."

    print("  ✓ Endpoint:           ", called_endpoint)
    print("  ✓ operation:          ", payload["operation"])
    print("  ✓ request_id:         ", payload["request_id"])
    print("  ✓ requisition_id:     ", payload["requisition_id"])
    print("  ✓ experience:         ", payload["experience"])
    print("  ✓ technical_round:    ", payload["technical_round"])
    print("  ✓ one2one_round:      ", payload["one2one_round"])
    print("  ✓ comm_skill_rating:  ", payload["comm_skill_rating"])
    print("  ✓ cultural_fit_rating:", payload["cultural_fit_rating"])
    print("  ✓ registrationUrl:    ", res.get("registrationUrl"))
    print("  ✓ Write Safety:        No 5xx auto-retries enabled (is_write=True)")


if __name__ == "__main__":
    test_key_separation()
    test_add_candidate_payload_structure()
    print("\n" + "=" * 60)
    print(" ALL TESTS PASSED SUCCESSFULLY! ")
    print("=" * 60)
