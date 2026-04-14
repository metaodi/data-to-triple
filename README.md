# data-to-triple

A **GitHub Actions pipeline** that converts relational CSV data to RDF triples
using a [LinkML](https://linkml.io/) schema, and optionally publishes the result
to an [Apache Jena Fuseki](https://jena.apache.org/documentation/fuseki2/)
SPARQL endpoint.

```
CSV  ──(LinkML schema)──►  RDF / Turtle  ──►  Fuseki triple store  ──►  SPARQL
```

---

## Repository layout

```
data-to-triple/
├── data/
│   └── persons.csv          # Sample relational data
├── schema/
│   └── persons.yaml         # LinkML schema (maps CSV columns → RDF properties)
├── scripts/
│   ├── convert.py           # CSV → Turtle conversion script
│   └── upload_to_fuseki.sh  # Upload Turtle to a Fuseki SPARQL endpoint
├── tests/
│   └── test_convert.py      # Pytest tests for the conversion logic
├── output/                  # Generated Turtle files (git-ignored)
├── .github/workflows/
│   └── data-to-triple.yml   # GitHub Actions workflow
├── docker-compose.yml       # Local Fuseki triple store
├── requirements.txt         # Python runtime dependencies
└── requirements-dev.txt     # Development / test dependencies
```

---

## How it works

### 1 · Define a LinkML schema

`schema/persons.yaml` describes the data model using the
[LinkML specification](https://linkml.io/linkml-model/docs/):

```yaml
classes:
  Person:
    class_uri: schema:Person   # maps the class to schema.org/Person
    attributes:
      id:
        identifier: true       # used as the RDF subject URI
        range: uriorcurie
      name:
        slot_uri: schema:name  # maps the column to schema.org/name
      age:
        slot_uri: schema:age
        range: integer
      email:
        slot_uri: schema:email
```

### 2 · Prepare your CSV

`data/persons.csv` is plain relational data – column names match attribute
names in the schema:

```csv
id,name,age,email
P001,Alice Smith,30,alice@example.com
P002,Bob Jones,25,bob@example.com
```

### 3 · Convert to RDF

```bash
pip install -r requirements.txt
python scripts/convert.py
```

The generated `output/persons.ttl` is valid Turtle RDF:

```turtle
@prefix ex:      <https://example.org/> .
@prefix schema1: <http://schema.org/> .

ex:P001 a schema1:Person ;
    schema1:age   30 ;
    schema1:email "alice@example.com"^^xsd:string ;
    schema1:name  "Alice Smith"^^xsd:string .
```

CLI options are available if you want to point at different files:

```bash
python scripts/convert.py \
  --csv     data/persons.csv \
  --schema  schema/persons.yaml \
  --output  output/persons.ttl \
  --class   Person \
  --id-prefix https://example.org/
```

### 4 · Publish to a SPARQL endpoint (optional)

#### Local (Docker Compose)

```bash
# Start Fuseki
docker compose up -d

# Upload the generated Turtle
bash scripts/upload_to_fuseki.sh

# Open the Fuseki web UI
open http://localhost:3030
```

#### Query with SPARQL

```bash
curl -G http://localhost:3030/persons/sparql \
  --data-urlencode 'query=PREFIX schema: <http://schema.org/>
    SELECT ?name ?age WHERE { ?p schema:name ?name ; schema:age ?age }' \
  -H "Accept: application/sparql-results+json" \
  -u admin:admin
```

---

## GitHub Actions pipeline

The workflow `.github/workflows/data-to-triple.yml` runs automatically when
`data/`, `schema/`, or `scripts/` change (push to `main` or pull request).
It can also be triggered manually via **Actions → Data to Triple → Run workflow**.

| Job | What it does |
|-----|--------------|
| **convert** | Installs dependencies, runs tests, converts CSV → Turtle, uploads the Turtle file as a workflow artifact. |
| **publish** | Downloads the artifact, starts Fuseki as a service container, uploads the Turtle, and runs a SPARQL verification query. |

---

## Running tests

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest tests/ -v
```

---

## Adding a new dataset

1. Add your CSV to `data/`.
2. Create a matching LinkML schema in `schema/`.
3. Call `convert()` from `scripts/convert.py` (or run the CLI with `--csv`,
   `--schema`, `--output`, and `--class` flags pointing to the new files).
4. Push – the GitHub Actions pipeline handles the rest.
