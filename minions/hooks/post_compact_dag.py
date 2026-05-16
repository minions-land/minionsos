#!/usr/bin/env python3
"""PostCompact hook: extract DAG-worthy nodes from compact summary.

Reads the compact summary from stdin (JSON with 'compact_summary' field),
parses it for node references and typed entries, and appends any new nodes
to the project's journal.jsonl for later DAG ingestion.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path

logging.basicConfig(stream=sys.stderr, level=logging.DEBUG, format="%(levelname)s: %(message)s")
log = logging.getLogger("post_compact_dag")

# Patterns for node references and typed entries
NODE_REF_RE = re.compile(r"\[(H-\d+|E-\d+|R-\d+|D-\d+)\]")
TYPED_ENTRY_RE = re.compile(
    r"^[-*]\s*(hypothesis|experiment|result|dead_end):\s*(.+)",
    re.IGNORECASE | re.MULTILINE,
)
STATUS_RE = re.compile(r"\((tentative|verified|refuted|abandoned)\)", re.IGNORECASE)


def find_project_dir() -> Path | None:
    """Locate the project directory from MINIONS_PROJECT_PORT."""
    port = os.environ.get("MINIONS_PROJECT_PORT")
    if not port:
        log.debug("MINIONS_PROJECT_PORT not set, skipping")
        return None

    # Walk up from CWD or use MINIONS_ROOT to find project_{port}/
    minions_root = os.environ.get("MINIONS_ROOT")
    if minions_root:
        candidate = Path(minions_root).parent / f"project_{port}"
    else:
        # Try relative to this script's grandparent (MinionsOS repo root)
        candidate = Path(__file__).resolve().parent.parent.parent / f"project_{port}"

    if candidate.is_dir():
        return candidate

    log.debug("Project directory not found: %s", candidate)
    return None


def load_existing_node_ids(project_dir: Path) -> set[str]:
    """Load node IDs already present in dag.json."""
    dag_path = project_dir / "dag.json"
    if not dag_path.exists():
        return set()

    try:
        data = json.loads(dag_path.read_text(encoding="utf-8"))
        ids: set[str] = set()
        for node in data.get("nodes", []):
            node_id = node.get("id", "")
            if node_id:
                ids.add(node_id)
        return ids
    except (json.JSONDecodeError, OSError) as exc:
        log.debug("Could not read dag.json: %s", exc)
        return set()


def extract_nodes_from_summary(summary: str) -> list[dict]:
    """Extract DAG-worthy nodes from the compact summary text."""
    nodes: list[dict] = []
    seen_ids: set[str] = set()

    # Extract explicitly typed entries (- hypothesis: ..., - experiment: ..., etc.)
    for match in TYPED_ENTRY_RE.finditer(summary):
        node_type = match.group(1).lower()
        description = match.group(2).strip()

        # Check for an inline node ID
        id_match = NODE_REF_RE.search(description)
        node_id = id_match.group(1) if id_match else None

        # Check for status annotation
        status_match = STATUS_RE.search(description)
        status = status_match.group(1).lower() if status_match else "tentative"

        # Clean description of inline markers
        clean_desc = NODE_REF_RE.sub("", description).strip()
        clean_desc = STATUS_RE.sub("", clean_desc).strip()
        clean_desc = clean_desc.strip(" -—:")

        if node_id and node_id in seen_ids:
            continue
        if node_id:
            seen_ids.add(node_id)

        nodes.append(
            {
                "id": node_id,
                "type": node_type,
                "description": clean_desc,
                "status": status,
                "source": "post_compact",
            }
        )

    # Also pick up bare [H-xxx] references in context lines that weren't typed entries
    for match in NODE_REF_RE.finditer(summary):
        node_id = match.group(1)
        if node_id not in seen_ids:
            seen_ids.add(node_id)
            # Infer type from prefix
            prefix = node_id.split("-")[0]
            type_map = {"H": "hypothesis", "E": "experiment", "R": "result", "D": "dead_end"}
            nodes.append(
                {
                    "id": node_id,
                    "type": type_map.get(prefix, "unknown"),
                    "description": "",
                    "status": "tentative",
                    "source": "post_compact_ref_only",
                }
            )

    return nodes


def append_to_journal(project_dir: Path, nodes: list[dict]) -> int:
    """Append new nodes to journal.jsonl. Returns count written."""
    journal_path = project_dir / "journal.jsonl"
    count = 0

    try:
        with journal_path.open("a", encoding="utf-8") as f:
            for node in nodes:
                f.write(json.dumps(node, ensure_ascii=False) + "\n")
                count += 1
    except OSError as exc:
        log.error("Failed to write journal.jsonl: %s", exc)

    return count


def main() -> None:
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            log.debug("Empty stdin, nothing to do")
            return

        data = json.loads(raw)
        summary = data.get("compact_summary", "")
        if not summary:
            log.debug("No compact_summary field in input")
            return
    except (json.JSONDecodeError, KeyError) as exc:
        log.error("Failed to parse stdin: %s", exc)
        return

    project_dir = find_project_dir()
    if not project_dir:
        return

    # Extract nodes from the summary
    nodes = extract_nodes_from_summary(summary)
    if not nodes:
        log.debug("No DAG-worthy nodes found in compact summary")
        return

    # Filter out nodes already in dag.json
    existing_ids = load_existing_node_ids(project_dir)
    new_nodes = [n for n in nodes if n.get("id") is None or n["id"] not in existing_ids]

    if not new_nodes:
        log.debug("All extracted nodes already exist in dag.json")
        return

    count = append_to_journal(project_dir, new_nodes)
    log.debug("Appended %d new nodes to journal.jsonl", count)


if __name__ == "__main__":
    main()
