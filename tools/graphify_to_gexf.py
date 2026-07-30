#!/usr/bin/env python3
"""
Convert a Graphify merged-graph.json to GEXF format for Gephi.

Usage:
    python3 tools/graphify_to_gexf.py
    python3 tools/graphify_to_gexf.py --input graphify-out/merged-graph.json --output graphify-out/starship.gexf
"""

import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.dom import minidom


def convert(input_path: Path, output_path: Path) -> None:
    with open(input_path) as f:
        g = json.load(f)

    nodes = g.get("nodes", [])
    links = g.get("links", [])
    directed = g.get("directed", True)

    # Build id → index map (Graphify uses string IDs; GEXF needs stable refs)
    id_map: dict[str, int] = {n["id"]: i for i, n in enumerate(nodes)}

    # Root
    root = ET.Element("gexf", {
        "xmlns": "http://gexf.net/1.3",
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
        "xsi:schemaLocation": "http://gexf.net/1.3 http://gexf.net/1.3/gexf.xsd",
        "version": "1.3",
    })

    meta = ET.SubElement(root, "meta", {"lastmodifieddate": "2026-07-01"})
    ET.SubElement(meta, "creator").text = "graphify_to_gexf.py (MSN-0205A)"
    ET.SubElement(meta, "description").text = (
        f"Starship Endeavour engineering knowledge graph — "
        f"{len(nodes)} nodes, {len(links)} edges"
    )

    graph_el = ET.SubElement(root, "graph", {
        "defaultedgetype": "directed" if directed else "undirected",
        "mode": "static",
    })

    # ── Node attributes ──────────────────────────────────────────────────────
    node_attrs = ET.SubElement(graph_el, "attributes", {
        "class": "node",
        "mode": "static",
    })
    _attr(node_attrs, "0", "file_type",       "string")
    _attr(node_attrs, "1", "source_file",     "string")
    _attr(node_attrs, "2", "source_location", "string")
    _attr(node_attrs, "3", "community",       "integer")
    _attr(node_attrs, "4", "repo",            "string")
    _attr(node_attrs, "5", "origin",          "string")
    _attr(node_attrs, "6", "language",        "string")
    _attr(node_attrs, "7", "kind",            "string")
    _attr(node_attrs, "8", "norm_label",      "string")

    # ── Edge attributes ───────────────────────────────────────────────────────
    edge_attrs = ET.SubElement(graph_el, "attributes", {
        "class": "edge",
        "mode": "static",
    })
    _attr(edge_attrs, "0", "relation",         "string")
    _attr(edge_attrs, "1", "confidence",       "string")
    _attr(edge_attrs, "2", "confidence_score", "double")
    _attr(edge_attrs, "3", "source_file",      "string")
    _attr(edge_attrs, "4", "source_location",  "string")
    _attr(edge_attrs, "5", "context",          "string")

    # ── Nodes ─────────────────────────────────────────────────────────────────
    nodes_el = ET.SubElement(graph_el, "nodes")
    for i, n in enumerate(nodes):
        meta_inner = n.get("metadata") or {}
        node_el = ET.SubElement(nodes_el, "node", {
            "id": str(i),
            "label": n.get("label", n.get("id", str(i))),
        })
        avs = ET.SubElement(node_el, "attvalues")
        _av(avs, "0", n.get("file_type", ""))
        _av(avs, "1", n.get("source_file", ""))
        _av(avs, "2", n.get("source_location", ""))
        _av(avs, "3", str(n.get("community", -1)))
        _av(avs, "4", n.get("repo", ""))
        _av(avs, "5", n.get("_origin", ""))
        _av(avs, "6", meta_inner.get("language", ""))
        _av(avs, "7", meta_inner.get("kind", ""))
        _av(avs, "8", n.get("norm_label", ""))

    # ── Edges ─────────────────────────────────────────────────────────────────
    edges_el = ET.SubElement(graph_el, "edges")
    skipped = 0
    for i, lnk in enumerate(links):
        src_id = id_map.get(lnk.get("source", ""))
        tgt_id = id_map.get(lnk.get("target", ""))
        if src_id is None or tgt_id is None:
            skipped += 1
            continue
        edge_el = ET.SubElement(edges_el, "edge", {
            "id": str(i),
            "source": str(src_id),
            "target": str(tgt_id),
            "weight": str(float(lnk.get("weight", 1.0))),
            "label": str(lnk.get("relation", "")),
        })
        avs = ET.SubElement(edge_el, "attvalues")
        _av(avs, "0", lnk.get("relation", ""))
        _av(avs, "1", lnk.get("confidence", ""))
        _av(avs, "2", str(lnk.get("confidence_score", 1.0)))
        _av(avs, "3", lnk.get("source_file", ""))
        _av(avs, "4", lnk.get("source_location", ""))
        _av(avs, "5", lnk.get("context", ""))

    # ── Pretty-print XML ──────────────────────────────────────────────────────
    raw = ET.tostring(root, encoding="unicode")
    pretty = minidom.parseString(raw).toprettyxml(indent="  ", encoding="utf-8")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(pretty)

    print(f"Written: {output_path}")
    print(f"  Nodes : {len(nodes)}")
    print(f"  Edges : {len(links) - skipped}  ({skipped} skipped — dangling refs)")
    if skipped:
        print(f"  Note  : {skipped} edges had source/target not found in node list")


def _attr(parent: ET.Element, id_: str, title: str, type_: str) -> None:
    ET.SubElement(parent, "attribute", {"id": id_, "title": title, "type": type_})


def _av(parent: ET.Element, for_: str, value) -> None:
    s = "" if value is None else str(value)
    if s and s not in ("-1", ""):
        ET.SubElement(parent, "attvalue", {"for": for_, "value": s})


if __name__ == "__main__":
    repo = Path(__file__).parent.parent
    parser = argparse.ArgumentParser(description="Convert Graphify JSON to GEXF for Gephi")
    parser.add_argument("--input",  default=str(repo / "graphify-out/merged-graph.json"))
    parser.add_argument("--output", default=str(repo / "graphify-out/starship.gexf"))
    args = parser.parse_args()
    convert(Path(args.input), Path(args.output))
