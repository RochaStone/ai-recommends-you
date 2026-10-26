#!/bin/bash
# Builds dist/<name>.zip for Claude Cowork "Upload a skill". Excludes dev and private files.
set -eu
cd "$(dirname "$0")/.."
NAME=$(basename "$PWD")
mkdir -p dist
rm -f "dist/$NAME.zip"
zip -qr "dist/$NAME.zip" . -x ".git/*" "node_modules/*" ".venv/*" "dist/*" "out/*" "state/*" "__pycache__/*" "*.pyc" ".env*" ".DS_Store" "tests/fixtures/large/*"
echo "built dist/$NAME.zip ($(du -h "dist/$NAME.zip" | cut -f1))"
