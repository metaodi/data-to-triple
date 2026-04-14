#!/usr/bin/env bash
# upload_to_fuseki.sh
#
# Upload an RDF Turtle file to an Apache Jena Fuseki SPARQL endpoint.
#
# Usage:
#   ./scripts/upload_to_fuseki.sh [RDF_FILE] [DATASET] [FUSEKI_URL]
#
# Environment variables (override CLI positional args):
#   FUSEKI_URL    Base URL of the Fuseki server  (default: http://localhost:3030)
#   DATASET       Dataset name                   (default: persons)
#   ADMIN_USER    Admin username                  (default: admin)
#   ADMIN_PASSWORD Admin password                (default: admin)

set -euo pipefail

RDF_FILE="${1:-${RDF_FILE:-output/persons.ttl}}"
DATASET="${2:-${DATASET:-persons}}"
FUSEKI_URL="${3:-${FUSEKI_URL:-http://localhost:3030}}"
ADMIN_USER="${ADMIN_USER:-admin}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-admin}"

echo "Fuseki URL : ${FUSEKI_URL}"
echo "Dataset    : ${DATASET}"
echo "RDF file   : ${RDF_FILE}"

# ── Wait for Fuseki to be ready ─────────────────────────────────────────────
echo "Waiting for Fuseki..."
for i in $(seq 1 30); do
  if curl -sf "${FUSEKI_URL}/\$/ping" -u "${ADMIN_USER}:${ADMIN_PASSWORD}" > /dev/null 2>&1; then
    echo "Fuseki is ready."
    break
  fi
  echo "  attempt ${i}/30 – retrying in 3 s..."
  sleep 3
  if [ "$i" -eq 30 ]; then
    echo "ERROR: Fuseki did not become ready in time." >&2
    exit 1
  fi
done

# ── Create dataset (in-memory, idempotent) ───────────────────────────────────
echo "Creating dataset '${DATASET}'..."
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "${FUSEKI_URL}/\$/datasets" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "dbName=${DATASET}&dbType=mem" \
  -u "${ADMIN_USER}:${ADMIN_PASSWORD}")

if [ "${HTTP_STATUS}" -eq 200 ] || [ "${HTTP_STATUS}" -eq 409 ]; then
  echo "Dataset ready (HTTP ${HTTP_STATUS})."
else
  echo "ERROR: Failed to create dataset (HTTP ${HTTP_STATUS})." >&2
  exit 1
fi

# ── Upload RDF data ──────────────────────────────────────────────────────────
echo "Uploading ${RDF_FILE}..."
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "${FUSEKI_URL}/${DATASET}/data" \
  -H "Content-Type: text/turtle" \
  --data-binary "@${RDF_FILE}" \
  -u "${ADMIN_USER}:${ADMIN_PASSWORD}")

if [ "${HTTP_STATUS}" -eq 200 ] || [ "${HTTP_STATUS}" -eq 201 ]; then
  echo "Upload successful (HTTP ${HTTP_STATUS})."
else
  echo "ERROR: Upload failed (HTTP ${HTTP_STATUS})." >&2
  exit 1
fi

echo "Data is available at ${FUSEKI_URL}/${DATASET}/sparql"
