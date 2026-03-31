# Lambda AI Automation Starter

Production-ready starter for deploying AI-powered automation on AWS. Ships a Lambda function backed by Claude (Anthropic SDK) behind an API Gateway, with full Terraform infrastructure, CI/CD, and observability.

Built as a reference implementation by [Three Moons Network](https://threemoonsnetwork.net) — an AI consulting practice helping small businesses automate with production-grade systems.

## Architecture

```
                         ┌─────────────────────────────────────────┐
                         │              AWS Cloud                  │
                         │                                         │
  Client ──POST /task──▶ │  API Gateway ──▶ Lambda ──▶ Claude API  │
         ◀──── JSON ──── │  (HTTP API)      (Python)   (Anthropic) │
                         │       │              │                  │
                         │       ▼              ▼                  │
                         │  CloudWatch      CloudWatch             │
                         │  Access Logs     Logs + Alarms          │
                         │                                         │
                         │  SSM Parameter Store                    │
                         │  (API key, encrypted)                   │
                         └─────────────────────────────────────────┘
```

## What It Does

Send a JSON payload to the `/task` endpoint with one of four task types:

| Task | Description | Example Use Case |
|------|-------------|------------------|
| `summarize` | Condense text into key points | Meeting notes, long emails, reports |
| `classify` | Categorize input into labels | Support ticket triage, sentiment analysis |
| `extract` | Pull structured data from text | Invoice parsing, contact info extraction |
| `respond` | Generate a context-aware reply | Customer support, FAQ automation |

### Example Request

```bash
curl -X POST https://your-api-id.execute-api.us-east-1.amazonaws.com/task \
  -H "Content-Type: application/json" \
  -d '{
    "task": "summarize",
    "input_text": "Your long document text here..."
  }'
```

### Example Response

```json
{
  "task": "summarize",
  "result": "Key points from the document...",
  "model": "claude-sonnet-4-20250514",
  "usage": { "input_tokens": 150, "output_tokens": 85 },
  "latency_ms": 1240
}
```

## Quick Start

### Prerequisites

- AWS account with CLI configured
- Terraform >= 1.5
- Python 3.11+
- Anthropic API key ([console.anthropic.com](https://console.anthropic.com))

### 1. Clone and configure

```bash
git clone git@github.com:Three-Moons-Network/lambda-ai-automation.git
cd lambda-ai-automation
cp terraform/terraform.tfvars.example terraform/terraform.tfvars
# Edit terraform.tfvars with your API key and preferences
```

### 2. Build the Lambda package

```bash
./scripts/deploy.sh
```

### 3. Deploy

```bash
cd terraform
terraform init
terraform plan -out=tfplan
terraform apply tfplan
```

Terraform outputs the API endpoint URL. Test it:

```bash
API_URL=$(terraform output -raw invoke_url)

curl -X POST "$API_URL" \
  -H "Content-Type: application/json" \
  -d '{"task": "classify", "input_text": "I cannot log in to my account and I am very frustrated"}'
```

### 4. Tear down

```bash
terraform destroy
```

## Project Structure

```
├── src/
│   └── handler.py            # Lambda handler — task routing, validation, Claude calls
├── tests/
│   └── test_handler.py       # Unit tests with mocked Anthropic API
├── terraform/
│   ├── main.tf               # All infra: Lambda, API GW, IAM, SSM, CloudWatch
│   ├── outputs.tf            # Endpoint URL, function ARN, log group
│   ├── backend.tf            # Remote state config (commented for local use)
│   └── terraform.tfvars.example
├── scripts/
│   └── deploy.sh             # Build Lambda zip package
├── .github/workflows/
│   └── ci.yml                # Test, lint, TF validate, package
├── requirements.txt          # Runtime: anthropic SDK
└── requirements-dev.txt      # Dev: pytest, ruff
```

## Infrastructure Details

| Resource | Purpose |
|----------|---------|
| Lambda (Python 3.11) | Runs the handler, 256MB / 30s defaults |
| API Gateway HTTP API | REST endpoint with CORS, throttling (10 req/s burst 20) |
| SSM Parameter Store | Encrypted storage for the Anthropic API key |
| CloudWatch Log Groups | Lambda logs + API Gateway access logs |
| CloudWatch Alarms | Error count > 5 in 5min, p99 latency > 80% of timeout |
| IAM Role + Policy | Least-privilege: logs + SSM read only |

All resources are tagged with Project, Environment, ManagedBy, and Owner for cost tracking and governance.

## CI/CD

GitHub Actions runs on every push/PR to `main`:

- **Test** — `pytest` with mocked Anthropic calls (no API key needed in CI)
- **Lint** — `ruff format --check` + `ruff check`
- **Terraform Validate** — `fmt -check`, `init -backend=false`, `validate`
- **Package** — Builds `lambda.zip` artifact on main branch merges

## Customization

**Add a new task type:**

1. Add the task name to `ALLOWED_TASKS` in `handler.py`
2. Add a system prompt to `SYSTEM_PROMPTS`
3. Add tests in `test_handler.py`
4. That's it — the routing handles the rest

**Switch models:**

Set `anthropic_model` in your tfvars or pass it at plan time:

```bash
terraform plan -var="anthropic_model=claude-opus-4-20250514" -out=tfplan
```

**Add authentication:**

The API Gateway is currently open. For production, add a Lambda authorizer or API key requirement in `main.tf` under the `aws_apigatewayv2_route` resource.

## Cost Estimate

For low-volume usage (< 1,000 requests/month):

| Component | Estimated Monthly Cost |
|-----------|----------------------|
| Lambda | ~$0 (free tier: 1M requests, 400K GB-seconds) |
| API Gateway | ~$0 (free tier: 1M HTTP API calls) |
| CloudWatch | ~$0.50 (log storage) |
| Anthropic API | Usage-based (~$3/M input tokens, ~$15/M output tokens for Sonnet) |

**Total infrastructure: effectively free.** Your main cost is Anthropic API usage.

## Local Development

```bash
# Set up
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# Run tests
pytest tests/ -v

# Lint
ruff check src/ tests/
ruff format src/ tests/

# Test handler locally
export ANTHROPIC_API_KEY="sk-ant-..."
python -c "
from src.handler import lambda_handler
import json
event = {'body': json.dumps({'task': 'summarize', 'input_text': 'Test input'})}
print(json.dumps(json.loads(lambda_handler(event, None)['body']), indent=2))
"
```

## License

MIT

## Author

Charles Harvey ([linuxlsr](https://github.com/linuxlsr)) — [Three Moons Network LLC](https://threemoonsnetwork.net)
