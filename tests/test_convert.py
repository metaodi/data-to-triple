"""
Tests for scripts/convert.py

Run with:
    pytest tests/
"""

import csv
import io
import sys
from pathlib import Path

import pytest
from rdflib import RDF, XSD, Literal, URIRef
from rdflib.namespace import Namespace

# Add scripts directory to path so we can import convert
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from convert import build_rdf_graph, expand_curie, read_csv, convert  # noqa: E402

SCHEMA_FILE = Path(__file__).parent.parent / "schema" / "persons.yaml"
DATA_FILE = Path(__file__).parent.parent / "data" / "persons.csv"
ID_PREFIX = "https://example.org/"

SCHEMA = Namespace("http://schema.org/")
EX = Namespace("https://example.org/")


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def sample_rows():
    return [
        {"id": "P001", "name": "Alice Smith", "age": "30", "email": "alice@example.com"},
        {"id": "P002", "name": "Bob Jones", "age": "25", "email": "bob@example.com"},
    ]


@pytest.fixture
def sample_graph(sample_rows):
    return build_rdf_graph(sample_rows, SCHEMA_FILE, "Person", ID_PREFIX)


# ── Tests for expand_curie ───────────────────────────────────────────────────


def test_expand_curie_absolute_uri_unchanged():
    from linkml_runtime.utils.schemaview import SchemaView

    sv = SchemaView(str(SCHEMA_FILE))
    assert expand_curie("https://example.org/foo", sv) == "https://example.org/foo"


def test_expand_curie_known_prefix():
    from linkml_runtime.utils.schemaview import SchemaView

    sv = SchemaView(str(SCHEMA_FILE))
    result = expand_curie("schema:Person", sv)
    assert result == "http://schema.org/Person"


def test_expand_curie_unknown_returns_none():
    from linkml_runtime.utils.schemaview import SchemaView

    sv = SchemaView(str(SCHEMA_FILE))
    assert expand_curie("unknown:Foo", sv) is None


# ── Tests for read_csv ──────────────────────────────────────────────────────


def test_read_csv_returns_list_of_dicts(tmp_path):
    f = tmp_path / "test.csv"
    f.write_text("id,name\nX1,Alice\nX2,Bob\n")
    rows = read_csv(f)
    assert len(rows) == 2
    assert rows[0] == {"id": "X1", "name": "Alice"}


# ── Tests for build_rdf_graph ───────────────────────────────────────────────


def test_graph_has_correct_triple_count(sample_graph):
    # 2 rows × (rdf:type + name + age + email) = 2 × 4 = 8 triples
    assert len(sample_graph) == 8


def test_subjects_are_uris(sample_graph):
    subjects = set(sample_graph.subjects(RDF.type, SCHEMA.Person))
    assert URIRef("https://example.org/P001") in subjects
    assert URIRef("https://example.org/P002") in subjects


def test_rdf_type_triple(sample_graph):
    assert (URIRef(f"{ID_PREFIX}P001"), RDF.type, SCHEMA.Person) in sample_graph


def test_name_literal(sample_graph):
    alice = URIRef(f"{ID_PREFIX}P001")
    names = list(sample_graph.objects(alice, SCHEMA.name))
    assert len(names) == 1
    assert str(names[0]) == "Alice Smith"


def test_age_integer_datatype(sample_graph):
    alice = URIRef(f"{ID_PREFIX}P001")
    ages = list(sample_graph.objects(alice, SCHEMA.age))
    assert len(ages) == 1
    assert ages[0].datatype == XSD.integer
    assert int(ages[0]) == 30


def test_email_literal(sample_graph):
    bob = URIRef(f"{ID_PREFIX}P002")
    emails = list(sample_graph.objects(bob, SCHEMA.email))
    assert len(emails) == 1
    assert str(emails[0]) == "bob@example.com"


def test_missing_values_skipped(sample_graph):
    # Build a row with a missing email
    rows = [{"id": "P099", "name": "Nobody", "age": "20", "email": ""}]
    g = build_rdf_graph(rows, SCHEMA_FILE, "Person", ID_PREFIX)
    p099 = URIRef(f"{ID_PREFIX}P099")
    emails = list(g.objects(p099, SCHEMA.email))
    assert emails == []


def test_bare_id_prefixed(sample_graph):
    """IDs that are not full URIs should be expanded with the id_prefix."""
    assert (URIRef("https://example.org/P001"), RDF.type, SCHEMA.Person) in sample_graph


def test_full_uri_id_not_double_prefixed():
    rows = [{"id": "https://example.org/P999", "name": "Full URI", "age": "1", "email": "x@x.com"}]
    g = build_rdf_graph(rows, SCHEMA_FILE, "Person", ID_PREFIX)
    subject = URIRef("https://example.org/P999")
    assert (subject, RDF.type, SCHEMA.Person) in g
    # Make sure it's not https://example.org/https://example.org/P999
    assert (URIRef("https://example.org/https://example.org/P999"), RDF.type, SCHEMA.Person) not in g


# ── Tests for end-to-end convert ────────────────────────────────────────────


def test_convert_writes_turtle_file(tmp_path):
    out = tmp_path / "out.ttl"
    g = convert(DATA_FILE, SCHEMA_FILE, out, "Person", ID_PREFIX)
    assert out.exists()
    content = out.read_text()
    assert "@prefix" in content
    assert "schema:Person" in content or "schema1:Person" in content


def test_convert_creates_output_dir(tmp_path):
    out = tmp_path / "nested" / "dir" / "out.ttl"
    convert(DATA_FILE, SCHEMA_FILE, out, "Person", ID_PREFIX)
    assert out.exists()


def test_convert_triple_count(tmp_path):
    out = tmp_path / "out.ttl"
    g = convert(DATA_FILE, SCHEMA_FILE, out, "Person", ID_PREFIX)
    # data/persons.csv has 5 rows × 4 triples = 20
    assert len(g) == 20
