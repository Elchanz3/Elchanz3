#!/usr/bin/env bash
set -euo pipefail
rm -rf project
mkdir -p project
cat ci/chunks/part* | base64 -d | tar -xzf - -C project
