#!/usr/bin/env bash
# Re-install the magpie-base MoTR fork from GitHub (e.g. after upstream changes).
# Run from the project root. Also clear your browser cache afterwards.
set -euo pipefail
cd "$(dirname "$0")/.."
rm -rf package-lock.json node_modules/magpie-base
npm install
npm run build
