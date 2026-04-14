#!/usr/bin/env python3
"""
Convert CSV data to RDF triples using a LinkML schema.

This script reads a CSV file, maps each row to RDF triples based on the
class and property definitions in a LinkML YAML schema, and serializes
the result as Turtle (.ttl).

Usage:
    python scripts/convert.py
    python scripts/convert.py --csv data/persons.csv \\
        --schema schema/persons.yaml \\
        --output output/persons.ttl \\
        --class Person \\
        --id-prefix https://example.org/
"""

import argparse
import csv
import sys
from pathlib import Path

from rdflib import XSD, BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF

from linkml_runtime.utils.schemaview import SchemaView

# Default locations (relative to repo root)
REPO_ROOT = Path(__file__).parent.parent
DEFAULT_CSV = REPO_ROOT / "data" / "persons.csv"
DEFAULT_SCHEMA = REPO_ROOT / "schema" / "persons.yaml"
DEFAULT_OUTPUT = REPO_ROOT / "output" / "persons.ttl"
DEFAULT_CLASS = "Person"
DEFAULT_ID_PREFIX = "https://example.org/"

# Map LinkML built-in type names to XSD datatypes
_TYPE_TO_XSD = {
    "integer": XSD.integer,
    "int": XSD.integer,
    "float": XSD.float,
    "double": XSD.double,
    "boolean": XSD.boolean,
    "date": XSD.date,
    "datetime": XSD.dateTime,
    "uri": XSD.anyURI,
    "uriorcurie": XSD.anyURI,
    "string": XSD.string,
}


def expand_curie(curie, sv: SchemaView) -> str | None:
    """Expand a CURIE to a full URI using schema prefixes.

    :param curie: A CURIE (e.g. ``schema:Person``), a full URI (returned as-is),
        or ``None`` / empty string.
    :param sv: A :class:`SchemaView` whose prefix map is used for expansion.
    :returns: The expanded URI string, or ``None`` when *curie* is falsy or the
        prefix is not declared in the schema.
    """
    if not curie:
        return None
    s = str(curie)
    if s.startswith("http://") or s.startswith("https://"):
        return s
    if ":" in s:
        prefix, local = s.split(":", 1)
        if prefix in sv.schema.prefixes:
            return str(sv.schema.prefixes[prefix].prefix_reference) + local
    return None


def xsd_type_for_range(range_name: str, sv: SchemaView) -> URIRef:
    """Return the XSD datatype URIRef for a LinkML range name."""
    if range_name in _TYPE_TO_XSD:
        return _TYPE_TO_XSD[range_name]
    # Check custom types defined in the schema
    all_types = sv.all_types()
    if range_name in all_types:
        t = all_types[range_name]
        if t.uri:
            uri = expand_curie(t.uri, sv)
            if uri:
                return URIRef(uri)
    return XSD.string


def build_rdf_graph(
    rows: list[dict],
    schema_file: str | Path,
    class_name: str,
    id_prefix: str,
) -> Graph:
    """
    Convert a list of dicts (CSV rows) to an RDF graph using a LinkML schema.

    :param rows: CSV rows as a list of dicts (keyed by column name).
    :param schema_file: Path to the LinkML YAML schema.
    :param class_name: Name of the LinkML class each row represents.
    :param id_prefix: URI prefix prepended to bare identifier values.
    :returns: An rdflib Graph containing the converted triples.
    """
    sv = SchemaView(str(schema_file))
    g = Graph()

    # Bind all schema prefixes so the Turtle output uses short names
    for prefix, prefix_def in sv.schema.prefixes.items():
        g.bind(prefix, Namespace(str(prefix_def.prefix_reference)))

    cls = sv.get_class(class_name)
    class_uri = expand_curie(cls.class_uri, sv) if cls.class_uri else None

    # Build a slot lookup: column name → SlotDefinition
    slots = {s.name: s for s in sv.class_induced_slots(class_name)}
    id_slot = next((s for s in slots.values() if s.identifier), None)

    # Default namespace for properties without an explicit slot_uri
    default_ns_ref = sv.schema.prefixes.get(sv.schema.default_prefix)
    default_ns = str(default_ns_ref.prefix_reference) if default_ns_ref else "https://example.org/"

    for row in rows:
        # ── Subject URI ────────────────────────────────────────────────────────
        if id_slot and id_slot.name in row and row[id_slot.name]:
            raw_id = row[id_slot.name].strip()
            subject = URIRef(raw_id if raw_id.startswith("http") else id_prefix + raw_id)
        else:
            subject = BNode()

        # rdf:type triple
        if class_uri:
            g.add((subject, RDF.type, URIRef(class_uri)))

        # ── Property triples ───────────────────────────────────────────────────
        for slot_name, slot_def in slots.items():
            if slot_def.identifier:
                continue  # already handled as the subject
            if slot_name not in row or row[slot_name] is None or row[slot_name] == "":
                continue

            # Resolve property URI
            if slot_def.slot_uri:
                prop_uri = expand_curie(slot_def.slot_uri, sv)
            else:
                prop_uri = default_ns + slot_name
            if not prop_uri:
                continue

            prop = URIRef(prop_uri)
            raw_value = row[slot_name].strip()
            range_name = str(slot_def.range) if slot_def.range else "string"
            xsd_type = xsd_type_for_range(range_name, sv)

            # Cast and add the literal (or URI for anyURI ranges)
            try:
                if xsd_type == XSD.anyURI:
                    g.add((subject, prop, URIRef(raw_value)))
                elif xsd_type == XSD.integer:
                    g.add((subject, prop, Literal(int(raw_value), datatype=XSD.integer)))
                elif xsd_type in (XSD.float, XSD.double):
                    g.add((subject, prop, Literal(float(raw_value), datatype=xsd_type)))
                elif xsd_type == XSD.boolean:
                    g.add((subject, prop, Literal(raw_value.lower() in ("true", "1", "yes"), datatype=XSD.boolean)))
                else:
                    g.add((subject, prop, Literal(raw_value, datatype=XSD.string)))
            except (ValueError, TypeError) as exc:
                print(
                    f"Warning: could not cast '{raw_value}' for {slot_name} ({range_name}): {exc}",
                    file=sys.stderr,
                )

    return g


def read_csv(csv_file: str | Path) -> list[dict]:
    """Read a CSV file and return rows as a list of dicts."""
    with open(csv_file, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def convert(
    csv_file: str | Path,
    schema_file: str | Path,
    output_file: str | Path,
    class_name: str,
    id_prefix: str,
) -> Graph:
    """End-to-end conversion: CSV → Turtle RDF."""
    rows = read_csv(csv_file)
    g = build_rdf_graph(rows, schema_file, class_name, id_prefix)

    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    g.serialize(destination=str(output_file), format="turtle")

    print(f"Converted {len(rows)} rows → {len(g)} triples → {output_file}")
    return g


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Convert a CSV file to RDF Turtle using a LinkML schema."
    )
    parser.add_argument("--csv", default=str(DEFAULT_CSV), help="Path to input CSV file")
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA), help="Path to LinkML schema YAML")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Path for output Turtle file")
    parser.add_argument("--class", dest="class_name", default=DEFAULT_CLASS, help="LinkML class name for each row")
    parser.add_argument("--id-prefix", default=DEFAULT_ID_PREFIX, help="URI prefix for bare identifier values")

    args = parser.parse_args(argv)

    convert(
        csv_file=args.csv,
        schema_file=args.schema,
        output_file=args.output,
        class_name=args.class_name,
        id_prefix=args.id_prefix,
    )


if __name__ == "__main__":
    main()
