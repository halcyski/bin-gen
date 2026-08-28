#!/usr/bin/env bash
set -euo pipefail

docker build -t fwfuzz-generator .

./scripts/bin-target-generator.py targets.toml toolchains.toml \
	--docker \
	--image fwfuzz-generator \
	--execute \
	"$@"
