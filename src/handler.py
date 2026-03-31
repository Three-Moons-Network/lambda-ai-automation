"""
Lambda AI Automation — Request Handler

Receives events via API Gateway, routes them to the appropriate AI task,
and returns structured responses. Uses the Anthropic Claude API for inference.

Supported tasks:
  - summarize: Condense long text into key points
  - classify:  Categorize input into predefined labels
  - extract:   Pull structured data from unstructured text
  - respond:   Generate a context-aware reply (e.g., customer support)
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from typing import Any

import anthropic

logger = logging.getLogger(__name__)
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "1024"))
ALLOWED_TASKS = {"summarize", "classify", "extract", "respond"}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class TaskRequest:
    """Validated inbound request."""
    task: str
    input_text: str
    context: dict[str, Any] | None = None


@dataclass
class TaskResponse:
    """Structured outbound response."""
    task: str
    result: str
    model: str
    usage: dict[str, int]
    latency_ms: int


# ---------------------------------------------------------------------------
# System prompts per task
# ---------------------------------------------------------------------------

SYSTEM_PROMPTS: dict[str, str] = {
    "summarize": (
        "You are a concise summarizer. Given the input text, produce a clear summary "
        "with the most important points. Use bullet points for lists of 3+ items. "
        "Keep the summary under 200 words unless the input is exceptionally long."
    ),
    "classify": (
        "You are a text classifier. Given the input text, classify it into exactly one "
        "of the provided categories. Respond with ONLY a JSON object: "
        '{"label": "<category>", "confidence": <0.0-1.0>, "reasoning": "<one sentence>"}. '
        "If categories are not provided in context, use these defaults: "
        "positive, negative, neutral, question, request, complaint."
    ),
    "extract": (
        "You are a structured data extractor. Given the input text, extract all "
        "relevant entities and data points into a clean JSON object. Include keys for: "
        "names, dates, amounts, locations, and any domain-specific fields mentioned. "
        "Respond ONLY with valid JSON."
    ),
    "respond": (
        "You are a helpful, professional assistant responding on behalf of a small business. "
        "Use the provided context to tailor your response. Keep the tone warm but concise. "
        "If you lack information to answer fully, say so clearly rather than guessing."
    ),
}


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def validate_request(body: dict[str, Any]) -> TaskRequest:
    """Parse and validate the incoming request body."""
    task = body.get("task", "").strip().lower()
    if task not in ALLOWED_TASKS:
        raise ValueError(
            f"Invalid task '{task}'. Must be one of: {', '.join(sorted(ALLOWED_TASKS))}"
        )

    input_text = body.get("input_text", "").strip()
    if not input_text:
        raise ValueError("'input_text' is required and cannot be empty.")

    if len(input_text) > 100_000:
        raise ValueError("'input_text' exceeds maximum length of 100,000 characters.")

    context = body.get("context")
    if context is not None and not isinstance(context, dict):
        raise ValueError("'context' must be a JSON object if provided.")

    return TaskRequest(task=task, input_text=input_text, context=context)


def build_user_message(request: TaskRequest) -> str:
    """Assemble the user message from the request fields."""
    parts = [request.input_text]

    if request.context:
        parts.append(f"\n\nAdditional context:\n{json.dumps(request.context, indent=2)}")

    return "\n".join(parts)


def invoke_claude(request: TaskRequest) -> TaskResponse:
    """Call the Anthropic API and return a structured response."""
    client = anthropic.Anthropic()  # Uses ANTHROPIC_API_KEY env var

    system_prompt = SYSTEM_PROMPTS[request.task]
    user_message = build_user_message(request)

    start = time.monotonic()

    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=MAX_TOKENS,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    latency_ms = int((time.monotonic() - start) * 1000)

    result_text = response.content[0].text

    return TaskResponse(
        task=request.task,
        result=result_text,
        model=response.model,
        usage={
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        },
        latency_ms=latency_ms,
    )


# ---------------------------------------------------------------------------
# Lambda entry point
# ---------------------------------------------------------------------------

def lambda_handler(event: dict, context: Any) -> dict:
    """
    AWS Lambda handler for API Gateway (REST or HTTP API).

    Expects a JSON body with:
      - task:       str — one of: summarize, classify, extract, respond
      - input_text: str — the text to process
      - context:    dict (optional) — additional context for the task

    Returns:
      - 200 with TaskResponse JSON on success
      - 400 on validation errors
      - 500 on unexpected failures
    """
    logger.info("Received event", extra={"path": event.get("path"), "method": event.get("httpMethod")})

    try:
        # Parse body — API Gateway may pass string or dict
        body = event.get("body", "{}")
        if isinstance(body, str):
            body = json.loads(body)

        request = validate_request(body)
        result = invoke_claude(request)

        logger.info(
            "Task completed",
            extra={
                "task": result.task,
                "model": result.model,
                "latency_ms": result.latency_ms,
                "input_tokens": result.usage["input_tokens"],
                "output_tokens": result.usage["output_tokens"],
            },
        )

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps(asdict(result)),
        }

    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Validation error", extra={"error": str(exc)})
        return {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": str(exc)}),
        }

    except anthropic.APIError as exc:
        logger.error("Anthropic API error", extra={"error": str(exc), "status": getattr(exc, "status_code", None)})
        return {
            "statusCode": 502,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "AI service temporarily unavailable. Please retry."}),
        }

    except Exception:
        logger.exception("Unexpected error")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Internal server error"}),
        }
