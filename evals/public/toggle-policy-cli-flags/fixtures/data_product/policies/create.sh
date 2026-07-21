#!/usr/bin/env bash
# Creates the validation contract and activates the data-quality policy for
# shipment-events-curated. Run once per environment from this directory.
set -euo pipefail

CONFIG="${NXD_CONFIG:?set NXD_CONFIG to the session mesh config path}"
ENV_NAME="${1:?usage: create.sh <env>}"

nxd --config "$CONFIG" create contract --skip-version-check \
  --name shipment-events-output-quality \
  --code ./contracts/shipment_events_output_quality.py \
  --description "Freshness + non-null carrier checks on the curated shipment events port"

nxd --config "$CONFIG" activate policy --skip-version-check \
  --name require-shipment-output-quality \
  --policy DataQualityCompliance \
  --validation-url shipment-events-output-quality \
  --output-ports at-least-one \
  --filter '.name == "shipment-events-curated"' \
  --consequence STOP \
  --promise-enforced \
  --env "$ENV_NAME"
