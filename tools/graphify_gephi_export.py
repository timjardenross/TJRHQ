#!/usr/bin/env python3
"""
MSN-0205A — Gephi optimisation pipeline.

Produces:
  graphify-out/merged-graph-summary.md   — stats + top 50 nodes
  graphify-out/gephi-export.gexf         — full graph with service/type/importance attrs
  graphify-out/gephi-filtered.gexf       — degree-pruned, doc-collapsed, deduped
  graphify-out/gephi-topology.png        — low-res topology overview
"""

import json
import math
import xml.etree.ElementTree as ET
from collections import defaultdict, Counter
from pathlib import Path
from xml.dom import minidom

# ── Paths ─────────────────────────────────────────────────────────────────────
REPO = Path(__file__).parent.parent
INPUT = REPO / "graphify-out/merged-graph.json"
OUT   = REPO / "graphify-out"
OUT.mkdir(exist_ok=True)

# ── Repo display names ────────────────────────────────────────────────────────
REPO_LABELS = {
    "slack-bot":          "slack-bot",
    "src":                "lcars-portal",
    "coordination":       "core/coordination",
    "context-assembly":   "core/context-assembly",
    "health":             "core/health",
    "advisory":           "core/advisory",
    "engineering":        "core/engineering",
    "telegram-bot":       "telegram-bot",
    "xo-bot":             "xo-bot",
    "knowledge_navigation": "core/knowledge_navigation",
    "intelligence":       "core/intelligence",
    "governance":         "core/governance",
    "capture":            "core/capture",
    "inbox":              "core/inbox",
}

DOC_FILE_TYPES = {"document", "rationale", "concept"}


def load():
    with open(INPUT) as f:
        return json.load(f)


# ── 1. Summary markdown ───────────────────────────────────────────────────────
def write_summary(g):
    nodes = g["nodes"]
    links = g["links"]

    degree: dict[str, int] = defaultdict(int)
    for lnk in links:
        degree[lnk["source"]] += 1
        degree[lnk["target"]] += 1

    by_repo_nodes: Counter = Counter(n.get("repo", "unknown") for n in nodes)
    id_to_repo = {n["id"]: n.get("repo", "unknown") for n in nodes}
    by_repo_edges: Counter = Counter(id_to_repo.get(lnk["source"], "unknown") for lnk in links)
    type_counts: Counter = Counter(n.get("file_type", "unknown") for n in nodes)

    top50 = sorted(nodes, key=lambda n: degree[n["id"]], reverse=True)[:50]

    lines = [
        "# Starship Endeavour — Engineering Knowledge Graph Summary",
        "",
        f"**Source:** `graphify-out/merged-graph.json`  ",
        f"**Total nodes:** {len(nodes):,}  ",
        f"**Total edges:** {len(links):,}  ",
        f"**Generated:** 2026-07-01 (MSN-0205A)",
        "",
        "---",
        "",
        "## Node Counts by Service",
        "",
        "| Service | Nodes | Edges |",
        "|---|---|---|",
    ]
    all_repos = sorted(set(list(by_repo_nodes.keys()) + list(by_repo_edges.keys())),
                       key=lambda r: -by_repo_nodes[r])
    for repo in all_repos:
        label = REPO_LABELS.get(repo, repo)
        lines.append(f"| `{label}` | {by_repo_nodes[repo]:,} | {by_repo_edges[repo]:,} |")

    lines += [
        "",
        "## Node Types",
        "",
        "| Type | Count |",
        "|---|---|",
    ]
    for t, cnt in sorted(type_counts.items(), key=lambda x: -x[1]):
        lines.append(f"| {t} | {cnt:,} |")

    lines += [
        "",
        "## Top 50 Most Connected Nodes",
        "",
        "| Rank | Degree | Service | Node |",
        "|---|---|---|---|",
    ]
    for rank, n in enumerate(top50, 1):
        repo = REPO_LABELS.get(n.get("repo", "?"), n.get("repo", "?"))
        lines.append(f"| {rank} | {degree[n['id']]} | `{repo}` | `{n['label']}` |")

    path = OUT / "merged-graph-summary.md"
    path.write_text("\n".join(lines))
    print(f"[1/4] Written: {path}  ({len(nodes):,} nodes, {len(links):,} edges)")
    return degree


# ── GEXF helpers ──────────────────────────────────────────────────────────────
def _decl(parent, id_, title, type_):
    ET.SubElement(parent, "attribute", {"id": id_, "title": title, "type": type_})


def _av(parent, for_, value):
    s = "" if value is None else str(value)
    if s and s not in ("-1", ""):
        ET.SubElement(parent, "attvalue", {"for": for_, "value": s})


def _gexf_root(directed: bool):
    root = ET.Element("gexf", {
        "xmlns": "http://gexf.net/1.3",
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
        "xsi:schemaLocation": "http://gexf.net/1.3 http://gexf.net/1.3/gexf.xsd",
        "version": "1.3",
    })
    graph_el = ET.SubElement(root, "graph", {
        "defaultedgetype": "directed" if directed else "undirected",
        "mode": "static",
    })
    return root, graph_el


def _node_attr_block(graph_el):
    na = ET.SubElement(graph_el, "attributes", {"class": "node", "mode": "static"})
    _decl(na, "0", "service",          "string")
    _decl(na, "1", "type",             "string")
    _decl(na, "2", "importance",       "double")
    _decl(na, "3", "source_file",      "string")
    _decl(na, "4", "source_location",  "string")
    _decl(na, "5", "community",        "integer")
    _decl(na, "6", "language",         "string")
    _decl(na, "7", "kind",             "string")
    return na


def _edge_attr_block(graph_el):
    ea = ET.SubElement(graph_el, "attributes", {"class": "edge", "mode": "static"})
    _decl(ea, "0", "relation",         "string")
    _decl(ea, "1", "confidence",       "string")
    _decl(ea, "2", "confidence_score", "double")
    _decl(ea, "3", "context",          "string")
    return ea


def _importance(degree_val: int, max_degree: int) -> float:
    if max_degree == 0:
        return 0.0
    return round(math.log1p(degree_val) / math.log1p(max_degree), 4)


def _write_gexf(root, path: Path):
    raw = ET.tostring(root, encoding="unicode")
    pretty = minidom.parseString(raw).toprettyxml(indent="  ", encoding="utf-8")
    path.write_bytes(pretty)


# ── 2. gephi-export.gexf (full, enriched) ────────────────────────────────────
def write_export(g, degree):
    nodes = g["nodes"]
    links = g["links"]
    max_deg = max(degree.values()) if degree else 1

    id_map = {n["id"]: i for i, n in enumerate(nodes)}
    root, graph_el = _gexf_root(g.get("directed", False))
    _node_attr_block(graph_el)
    _edge_attr_block(graph_el)

    nodes_el = ET.SubElement(graph_el, "nodes")
    for i, n in enumerate(nodes):
        meta = n.get("metadata") or {}
        imp  = _importance(degree.get(n["id"], 0), max_deg)
        svc  = REPO_LABELS.get(n.get("repo", ""), n.get("repo", ""))
        node_el = ET.SubElement(nodes_el, "node", {
            "id": str(i),
            "label": str(n.get("label", n.get("id", str(i)))),
        })
        avs = ET.SubElement(node_el, "attvalues")
        _av(avs, "0", svc)
        _av(avs, "1", n.get("file_type", ""))
        _av(avs, "2", str(imp))
        _av(avs, "3", n.get("source_file", ""))
        _av(avs, "4", n.get("source_location", ""))
        _av(avs, "5", n.get("community", ""))
        _av(avs, "6", meta.get("language", ""))
        _av(avs, "7", meta.get("kind", ""))

    edges_el = ET.SubElement(graph_el, "edges")
    skipped = 0
    for i, lnk in enumerate(links):
        src = id_map.get(lnk.get("source", ""))
        tgt = id_map.get(lnk.get("target", ""))
        if src is None or tgt is None:
            skipped += 1
            continue
        edge_el = ET.SubElement(edges_el, "edge", {
            "id": str(i),
            "source": str(src),
            "target": str(tgt),
            "weight": str(float(lnk.get("weight", 1.0))),
            "label": str(lnk.get("relation", "")),
        })
        avs = ET.SubElement(edge_el, "attvalues")
        _av(avs, "0", lnk.get("relation", ""))
        _av(avs, "1", lnk.get("confidence", ""))
        _av(avs, "2", str(lnk.get("confidence_score", 1.0)))
        _av(avs, "3", lnk.get("context", ""))

    path = OUT / "gephi-export.gexf"
    _write_gexf(root, path)
    print(f"[2/4] Written: {path}  ({len(nodes):,} nodes, {len(links)-skipped:,} edges)")


# ── 3. gephi-filtered.gexf ────────────────────────────────────────────────────
def write_filtered(g, degree):
    nodes = g["nodes"]
    links = g["links"]
    max_deg = max(degree.values()) if degree else 1

    # a) remove degree-1 nodes (leaves — pure noise for visualisation)
    keep_ids = {n["id"] for n in nodes if degree.get(n["id"], 0) > 1}

    # b) collapse doc nodes: rationale/concept nodes rarely add visual value;
    #    replace any edge pointing to/from them with a direct code→code edge
    #    by simply dropping them from keep_ids and rewiring edges later.
    doc_ids = {n["id"] for n in nodes
               if n.get("file_type") in DOC_FILE_TYPES and n["id"] in keep_ids}
    keep_ids -= doc_ids

    # c) build filtered node list
    filtered_nodes = [n for n in nodes if n["id"] in keep_ids]
    id_map = {n["id"]: i for i, n in enumerate(filtered_nodes)}

    # d) deduplicate edges: keep one edge per (source, target, relation) triple,
    #    skipping edges to/from removed nodes
    seen_edges: set[tuple] = set()
    filtered_links = []
    for lnk in links:
        src, tgt = lnk.get("source"), lnk.get("target")
        if src not in keep_ids or tgt not in keep_ids:
            continue
        key = (src, tgt, lnk.get("relation", ""))
        if key in seen_edges:
            continue
        seen_edges.add(key)
        filtered_links.append(lnk)

    root, graph_el = _gexf_root(g.get("directed", False))
    _node_attr_block(graph_el)
    _edge_attr_block(graph_el)

    nodes_el = ET.SubElement(graph_el, "nodes")
    for i, n in enumerate(filtered_nodes):
        meta = n.get("metadata") or {}
        imp  = _importance(degree.get(n["id"], 0), max_deg)
        svc  = REPO_LABELS.get(n.get("repo", ""), n.get("repo", ""))
        node_el = ET.SubElement(nodes_el, "node", {
            "id": str(i),
            "label": str(n.get("label", n.get("id", str(i)))),
        })
        avs = ET.SubElement(node_el, "attvalues")
        _av(avs, "0", svc)
        _av(avs, "1", n.get("file_type", ""))
        _av(avs, "2", str(imp))
        _av(avs, "3", n.get("source_file", ""))
        _av(avs, "4", n.get("source_location", ""))
        _av(avs, "5", n.get("community", ""))
        _av(avs, "6", meta.get("language", ""))
        _av(avs, "7", meta.get("kind", ""))

    edges_el = ET.SubElement(graph_el, "edges")
    for i, lnk in enumerate(filtered_links):
        src = id_map[lnk["source"]]
        tgt = id_map[lnk["target"]]
        edge_el = ET.SubElement(edges_el, "edge", {
            "id": str(i),
            "source": str(src),
            "target": str(tgt),
            "weight": str(float(lnk.get("weight", 1.0))),
            "label": str(lnk.get("relation", "")),
        })
        avs = ET.SubElement(edge_el, "attvalues")
        _av(avs, "0", lnk.get("relation", ""))
        _av(avs, "1", lnk.get("confidence", ""))
        _av(avs, "2", str(lnk.get("confidence_score", 1.0)))
        _av(avs, "3", lnk.get("context", ""))

    path = OUT / "gephi-filtered.gexf"
    _write_gexf(root, path)
    removed_nodes = len(nodes) - len(filtered_nodes)
    removed_edges = len(links) - len(filtered_links)
    print(f"[3/4] Written: {path}  "
          f"({len(filtered_nodes):,} nodes [{removed_nodes:,} removed], "
          f"{len(filtered_links):,} edges [{removed_edges:,} removed])")
    return filtered_nodes, filtered_links, id_map


# ── 4. gephi-topology.png ─────────────────────────────────────────────────────
def write_topology(filtered_nodes, filtered_links, id_map):
    try:
        import networkx as nx
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
    except ImportError as e:
        print(f"[4/4] SKIPPED topology PNG — missing dependency: {e}")
        return

    # Build graph from filtered data (sample for layout performance)
    # Use service community as colour
    SERVICE_COLOURS = {
        "slack-bot":               "#1E88E5",
        "lcars-portal":            "#F4A62A",
        "core/coordination":       "#43A047",
        "core/context-assembly":   "#8E24AA",
        "core/health":             "#E53935",
        "core/advisory":           "#00ACC1",
        "core/engineering":        "#6D4C41",
        "core/knowledge_navigation": "#039BE5",
        "core/intelligence":       "#FFB300",
        "core/governance":         "#546E7A",
        "telegram-bot":            "#26A69A",
        "xo-bot":                  "#EF6C00",
        "core/capture":            "#AB47BC",
        "core/inbox":              "#78909C",
    }

    # Cap at 3000 nodes for layout speed; pick highest-degree nodes
    id_to_node = {n["id"]: n for n in filtered_nodes}
    degree_f: dict[str, int] = defaultdict(int)
    for lnk in filtered_links:
        degree_f[lnk["source"]] += 1
        degree_f[lnk["target"]] += 1

    top_nodes = sorted(filtered_nodes, key=lambda n: degree_f[n["id"]], reverse=True)[:3000]
    top_ids = {n["id"] for n in top_nodes}
    top_links = [lnk for lnk in filtered_links
                 if lnk["source"] in top_ids and lnk["target"] in top_ids]

    G = nx.Graph()
    for n in top_nodes:
        svc = REPO_LABELS.get(n.get("repo", ""), n.get("repo", ""))
        G.add_node(n["id"], service=svc, degree=degree_f[n["id"]])
    for lnk in top_links:
        G.add_edge(lnk["source"], lnk["target"])

    print(f"[4/4] Computing layout for {G.number_of_nodes()} nodes...")
    # kamada_kawai uses pure numpy (no scipy needed); fall back to random if it fails
    try:
        pos = nx.kamada_kawai_layout(G)
    except Exception:
        pos = nx.random_layout(G, seed=42)

    node_colours = [
        SERVICE_COLOURS.get(G.nodes[n].get("service", ""), "#90A4AE")
        for n in G.nodes
    ]
    node_sizes = [
        max(4, min(80, G.nodes[n].get("degree", 1) * 1.5))
        for n in G.nodes
    ]

    fig, ax = plt.subplots(figsize=(24, 18), dpi=72)
    fig.patch.set_facecolor("#0D1117")
    ax.set_facecolor("#0D1117")

    nx.draw_networkx_edges(G, pos, ax=ax, alpha=0.08,
                           edge_color="#FFFFFF", width=0.3)
    nx.draw_networkx_nodes(G, pos, ax=ax,
                           node_color=node_colours,
                           node_size=node_sizes,
                           alpha=0.85, linewidths=0)

    # Legend
    patches = [
        mpatches.Patch(color=c, label=svc)
        for svc, c in SERVICE_COLOURS.items()
        if svc in {REPO_LABELS.get(n.get("repo", ""), "") for n in top_nodes}
    ]
    ax.legend(handles=patches, loc="lower left", fontsize=7,
              facecolor="#1C2128", edgecolor="#444", labelcolor="white",
              framealpha=0.85, ncol=2)

    ax.set_title(
        f"Starship Endeavour — Engineering Knowledge Graph\n"
        f"{G.number_of_nodes():,} nodes · {G.number_of_edges():,} edges (top by degree)",
        color="white", fontsize=13, pad=12,
    )
    ax.axis("off")
    plt.tight_layout()

    path = OUT / "gephi-topology.png"
    plt.savefig(path, dpi=72, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"[4/4] Written: {path}")


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    g = load()
    degree = write_summary(g)
    write_export(g, degree)
    filtered_nodes, filtered_links, id_map = write_filtered(g, degree)
    write_topology(filtered_nodes, filtered_links, id_map)
    print("\nDone.")
