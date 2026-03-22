#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
git config core.hooksPath .githooks
echo "Installed git hooks from .githooks/"
