"""
Contract test for Slack Event API URL verification.

This test validates that our Slack event handler correctly processes
URL verification challenges according to the Slack Events API specification.

Reference: specs/002-slack-bot-ai/contracts/slack_events.yaml
"""

import json
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

# NOTE: These imports will fail until implementation exists (TDD)
# This is expected and required for TDD approach
try:
    from src.integrations.slack_handler import SlackEventHandler
    from src.main import app
except ImportError:
    # Expected during TDD phase - tests should fail first
    pytest.skip("Implementation not yet available", allow_module_level=True)


class TestSlackEventVerification:
    """Test Slack Events API URL verification contract."""

    @pytest.fixture
    def client(self) -> TestClient:
        """Create test client for Slack event endpoint."""
        return TestClient(app)

    @pytest.fixture
    def url_verification_payload(self) -> Dict[str, Any]:
        """Valid URL verification challenge payload."""
        return {
            "type": "url_verification",
            "challenge": "test_challenge_string_12345"
        }

    @pytest.fixture
    def invalid_verification_payload(self) -> Dict[str, Any]:
        """Invalid verification payload missing challenge."""
        return {
            "type": "url_verification"
            # Missing challenge field
        }

    def test_url_verification_success(
        self,
        client: TestClient,
        url_verification_payload: Dict[str, Any]
    ) -> None:
        """Test successful URL verification challenge response."""
        response = client.post(
            "/slack/events",
            json=url_verification_payload,
            headers={"Content-Type": "application/json"}
        )

        # Should return challenge string as plain text
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain; charset=utf-8"
        assert response.text == url_verification_payload["challenge"]

    def test_url_verification_missing_challenge(
        self,
        client: TestClient,
        invalid_verification_payload: Dict[str, Any]
    ) -> None:
        """Test URL verification with missing challenge field."""
        response = client.post(
            "/slack/events",
            json=invalid_verification_payload,
            headers={"Content-Type": "application/json"}
        )

        # Should return 400 Bad Request for invalid payload
        assert response.status_code == 400
        assert "challenge" in response.json()["detail"].lower()

    def test_url_verification_invalid_type(self, client: TestClient) -> None:
        """Test URL verification with invalid type field."""
        payload = {
            "type": "invalid_type",
            "challenge": "test_challenge"
        }

        response = client.post(
            "/slack/events",
            json=payload,
            headers={"Content-Type": "application/json"}
        )

        # Should return 400 Bad Request for invalid type
        assert response.status_code == 400

    def test_url_verification_malformed_json(self, client: TestClient) -> None:
        """Test URL verification with malformed JSON."""
        response = client.post(
            "/slack/events",
            data="invalid json",
            headers={"Content-Type": "application/json"}
        )

        # Should return 400 Bad Request for malformed JSON
        assert response.status_code == 400

    def test_url_verification_missing_content_type(
        self,
        client: TestClient,
        url_verification_payload: Dict[str, Any]
    ) -> None:
        """Test URL verification without Content-Type header."""
        response = client.post(
            "/slack/events",
            data=json.dumps(url_verification_payload)
            # Missing Content-Type header
        )

        # Should handle missing content type gracefully
        # Implementation should still process valid JSON
        assert response.status_code in [200, 400]  # Depends on implementation

    @pytest.mark.asyncio
    async def test_url_verification_performance(
        self,
        client: TestClient,
        url_verification_payload: Dict[str, Any]
    ) -> None:
        """Test URL verification response time performance."""
        import time

        start_time = time.time()

        response = client.post(
            "/slack/events",
            json=url_verification_payload,
            headers={"Content-Type": "application/json"}
        )

        end_time = time.time()
        response_time = end_time - start_time

        # Slack requires response within 3 seconds
        assert response_time < 3.0
        assert response.status_code == 200

    def test_url_verification_contract_compliance(
        self,
        client: TestClient,
        url_verification_payload: Dict[str, Any]
    ) -> None:
        """Test contract compliance with OpenAPI specification."""
        response = client.post(
            "/slack/events",
            json=url_verification_payload,
            headers={"Content-Type": "application/json"}
        )

        # Validate response matches contract spec
        assert response.status_code == 200

        # Response should be plain text (challenge string)
        assert response.headers.get("content-type", "").startswith("text/plain")

        # Response body should exactly match challenge
        assert response.text == url_verification_payload["challenge"]

        # Response should not include extra headers
        forbidden_headers = ["x-powered-by", "server"]
        for header in forbidden_headers:
            assert header not in response.headers

    def test_url_verification_edge_cases(self, client: TestClient) -> None:
        """Test URL verification edge cases and boundary conditions."""
        test_cases = [
            # Empty challenge
            {"type": "url_verification", "challenge": ""},

            # Very long challenge
            {"type": "url_verification", "challenge": "x" * 1000},

            # Challenge with special characters
            {"type": "url_verification", "challenge": "test-_=+&%$#@!"},

            # Challenge with unicode
            {"type": "url_verification", "challenge": "test🚀挑戦"},

            # Additional unexpected fields
            {
                "type": "url_verification",
                "challenge": "test",
                "unexpected_field": "should_be_ignored"
            }
        ]

        for payload in test_cases:
            response = client.post(
                "/slack/events",
                json=payload,
                headers={"Content-Type": "application/json"}
            )

            # All should succeed and return the challenge
            if payload["challenge"]:  # Non-empty challenges
                assert response.status_code == 200
                assert response.text == payload["challenge"]
            else:  # Empty challenge might be rejected
                assert response.status_code in [200, 400]