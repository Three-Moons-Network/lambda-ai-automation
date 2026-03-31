#!/usr/bin/env bash
set -euo pipefail

# Build Lambda deployment package locally.
# Usage: ./scripts/deploy.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "==> Cleaning previous build"
rm -rf "$PROJECT_DIR/dist"
mkdir -p "$PROJECT_DIR/dist/package"

echo "==> Installing dependencies"
pip install -r "$PROJECT_DIR/requirements.txt" -t "$PROJECT_DIR/dist/package/" --quiet

echo "==> Copying handler"
cp "$PROJECT_DIR/src/handler.py" "$PROJECT_DIR/dist/package/"

echo "==> Creating zip"
cd "$PROJECT_DIR/dist/package"
zip -r "$PROJECT_DIR/dist/lambda.zip" . -q

ZIPSIZE=$(du -h "$PROJECT_DIR/dist/lambda.zip" | cut -f1)
echo "==> Done: dist/lambda.zip ($ZIPSIZE)"
echo ""
echo "Next steps:"
echo "  cd terraform && terraform plan -out=tfplan"
echo "  terraform apply tfplan"
