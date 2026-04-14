#!/usr/bin/env bash
# upload_to_fuseki.sh
#
# Upload one or more RDF Turtle files to an Apache Jena Fuseki SPARQL endpoint.
#
# Usage:
#   ./scripts/upload_to_fuseki.sh [RDF_FILE ...] [DATASET] [FUSEKI_URL]
#
#   When called with a single file argument the dataset and URL are taken from
#   environment variables (or their defaults).  When called with multiple file
#   arguments all files are uploaded to the same dataset.
#
# Environment variables (always respected, override built-in defaults):
#   FUSEKI_URL    Base URL of the Fuseki server  (default: http://localhost:3030)
#   DATASET       Dataset name                   (default: persons)
#   ADMIN_USER    Admin username                  (default: admin)
#   ADMIN_PASSWORD Admin password                (default: admin)

set -euo pipefail

# ── Positional-argument handling ─────────────────────────────────────────────
# For backward-compatibility a single positional argument is still treated as
# [RDF_FILE], two as [RDF_FILE DATASET], and three as [RDF_FILE DATASET URL].
# When more than one file is needed, pass them all as positional args and set
# DATASET / FUSEKI_URL via environment variables.
if [ "$#" -eq 0 ]; then
  RDF_FILES=("${RDF_FILE:-output/persons.ttl}")
elif [ "$#" -eq 1 ]; then
  RDF_FILES=("$1")
elif [ "$#" -eq 2 ]; then
  RDF_FILES=("$1")
  DATASET="${2}"
elif [ "$#" -eq 3 ] && [[ "$3" == http://* || "$3" == https://* ]]; then
  RDF_FILES=("$1")
  DATASET="${2}"
  FUSEKI_URL="${3}"
else
  # Multiple files – dataset/URL must come from env vars
  RDF_FILES=("$@")
fi

DATASET="${DATASET:-persons}"
FUSEKI_URL="${FUSEKI_URL:-http://localhost:3030}"
ADMIN_USER="${ADMIN_USER:-admin}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-admin}"

echo "Fuseki URL : ${FUSEKI_URL}"
echo "Dataset    : ${DATASET}"
echo "RDF files  : ${RDF_FILES[*]}"

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

# ── Upload RDF files ─────────────────────────────────────────────────────────
for RDF_FILE in "${RDF_FILES[@]}"; do
  echo "Uploading ${RDF_FILE}..."
  HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "${FUSEKI_URL}/${DATASET}/data" \
    -H "Content-Type: text/turtle" \
    --data-binary "@${RDF_FILE}" \
    -u "${ADMIN_USER}:${ADMIN_PASSWORD}")

  if [ "${HTTP_STATUS}" -eq 200 ] || [ "${HTTP_STATUS}" -eq 201 ]; then
    echo "Upload successful (HTTP ${HTTP_STATUS})."
  else
    echo "ERROR: Upload of ${RDF_FILE} failed (HTTP ${HTTP_STATUS})." >&2
    exit 1
  fi
done

echo "Data is available at ${FUSEKI_URL}/${DATASET}/sparql"
