"""
Tests for the Lambda AI automation handler.

Uses mocking to avoid real Anthropic API calls during CI.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from src.handler import (
    ALLOWED_TASKS,
    TaskRequest,
    build_user_message,
    lambda_handler,
    validate_request,
)


# ---------------------------------------------------------------------------
# validate_request
# ---------------------------------------------------------------------------

class TestValidateRequest:
    def test_valid_summarize(self):
        req = validate_request({"task": "summarize", "input_text": "Hello world"})
        assert req.task == "summarize"
        assert req.input_text == "Hello world"
        assert req.context is None

    def test_valid_with_context(self):
        req = validate_request({
            "task": "classify",
            "input_text": "I love this product",
            "context": {"categories": ["positive", "negative"]},
        })
        assert req.context == {"categories": ["positive", "negative"]}

    def test_all_tasks_accepted(self):
        for task in ALLOWED_TASKS:
            req = validate_request({"task": task, "input_text": "test"})
            assert req.task == task

    def test_invalid_task_raises(self):
        with pytest.raises(ValueError, match="Invalid task"):
            validate_request({"task": "dance", "input_text": "test"})

    def test_empty_task_raises(self):
        with pytest.raises(ValueError, match="Invalid task"):
            validate_request({"task": "", "input_text": "test"})

    def test_missing_input_text_raises(self):
        with pytest.raises(ValueError, match="input_text"):
            validate_request({"task": "summarize", "input_text": ""})

    def test_whitespace_only_input_raises(self):
        with pytest.raises(ValueError, match="input_text"):
            validate_request({"task": "summarize", "input_text": "   "})

    def test_oversized_input_raises(self):
        with pytest.raises(ValueError, match="maximum length"):
            validate_request({"task": "summarize", "input_text": "x" * 100_001})

    def test_invalid_context_type_raises(self):
        with pytest.raises(ValueError, match="context"):
            validate_request({"task": "summarize", "input_text": "test", "context": "not a dict"})

    def test_task_is_lowercased_and_stripped(self):
        req = validate_request({"task": "  SUMMARIZE  ", "input_text": "test"})
        assert req.task == "summarize"


# ---------------------------------------------------------------------------
# build_user_message
# ---------------------------------------------------------------------------

class TestBuildUserMessage:
    def test_simple_message(self):
        req = TaskRequest(task="summarize", input_text="Hello")
        assert build_user_message(req) == "Hello"

    def test_message_with_context(self):
        req = TaskRequest(task="classify", input_text="Hello", context={"labels": ["a", "b"]})
        msg = build_user_message(req)
        assert "Hello" in msg
        assert "Additional context" in msg
        assert '"labels"' in msg


# ---------------------------------------------------------------------------
# lambda_handler (integration with mocked Anthropic)
# ---------------------------------------------------------------------------

def _mock_anthropic_response(text: str = "Mock result") -> MagicMock:
    """Build a mock that mimics anthropic.messages.create() response."""
    response = MagicMock()
    response.content = [MagicMock(text=text)]
    response.model = "claude-sonnet-4-20250514"
    response.usage.input_tokens = 50
    response.usage.output_tokens = 30
    return response


class TestLambdaHandler:
    @patch("src.handler.anthropic.Anthropic")
    def test_successful_summarize(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_anthropic_response("Summary here")
        mock_client_cls.return_value = mock_client

        event = {
            "body": json.dumps({"task": "summarize", "input_text": "Long text to summarize"}),
            "path": "/task",
            "httpMethod": "POST",
        }

        result = lambda_handler(event, None)
        assert result["statusCode"] == 200

        body = json.loads(result["body"])
        assert body["task"] == "summarize"
        assert body["result"] == "Summary here"
        assert "usage" in body
        assert "latency_ms" in body

    @patch("src.handler.anthropic.Anthropic")
    def test_successful_classify(self, mock_client_cls):
        mock_response = '{"label": "positive", "confidence": 0.95, "reasoning": "upbeat tone"}'
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_anthropic_response(mock_response)
        mock_client_cls.return_value = mock_client

        event = {
            "body": json.dumps({"task": "classify", "input_text": "Great product!"}),
        }

        result = lambda_handler(event, None)
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["task"] == "classify"

    def test_invalid_task_returns_400(self):
        event = {
            "body": json.dumps({"task": "invalid", "input_text": "test"}),
        }
        result = lambda_handler(event, None)
        assert result["statusCode"] == 400
        assert "Invalid task" in json.loads(result["body"])["error"]

    def test_missing_body_returns_400(self):
        event = {"body": "not json {{{"}
        result = lambda_handler(event, None)
        assert result["statusCode"] == 400

    def test_empty_input_returns_400(self):
        event = {
            "body": json.dumps({"task": "summarize", "input_text": ""}),
        }
        result = lambda_handler(event, None)
        assert result["statusCode"] == 400

    @patch("src.handler.anthropic.Anthropic")
    def test_anthropic_api_error_returns_502(self, mock_client_cls):
        import anthropic as anthropic_mod

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = anthropic_mod.APIError(
            message="rate limited",
            request=MagicMock(),
            body=None,
        )
        mock_client_cls.return_value = mock_client

        event = {
            "body": json.dumps({"task": "summarize", "input_text": "test"}),
        }
        result = lambda_handler(event, None)
        assert result["statusCode"] == 502

    def test_cors_headers_present(self):
        event = {
            "body": json.dumps({"task": "bad_task", "input_text": "test"}),
        }
        result = lambda_handler(event, None)
        # Even error responses should have Content-Type
        assert result["headers"]["Content-Type"] == "application/json"

    @patch("src.handler.anthropic.Anthropic")
    def test_body_as_dict(self, mock_client_cls):
        """API Gateway v2 may pass body as already-parsed dict."""
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_anthropic_response()
        mock_client_cls.return_value = mock_client

        event = {
            "body": {"task": "extract", "input_text": "Name: John, Amount: $500"},
        }
        result = lambda_handler(event, None)
        assert result["statusCode"] == 200
