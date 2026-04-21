"""
ModernKnowledge — validate.py
Validates node files and lattice.json against schema.yaml.
"""

import yaml
import json
import sys
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent.parent / "schema" / "schema.yaml"


def load_schema():
    with open(SCHEMA_PATH) as f:
        return yaml.safe_load(f)


def validate_node(node: dict, schema: dict) -> list[str]:
    """Validate a single node dict against schema. Returns list of errors."""
    errors = []
    ntype = node.get("type")
    if not ntype:
        errors.append("Node missing 'type' field")
        return errors

    type_def = schema["node_types"].get(ntype)
    if not type_def:
        errors.append(f"Unknown node type: {ntype}")
        return errors

    for field in type_def["required_fields"]:
        if field not in node:
            errors.append(f"Node {node.get('id', '?')}: missing required field '{field}'")

    prefix = type_def.get("id_prefix", "")
    nid = node.get("id", "")
    if prefix and not nid.startswith(prefix):
        errors.append(f"Node {nid}: id should start with '{prefix}'")

    return errors


def validate_edge(edge: dict, schema: dict, node_ids: set) -> list[str]:
    """Validate a single edge dict. Returns list of errors."""
    errors = []
    for field in ("source", "target", "type"):
        if field not in edge:
            errors.append(f"Edge missing '{field}': {edge}")
            return errors

    if edge["source"] not in node_ids:
        errors.append(f"Edge source '{edge['source']}' not found in nodes")
    if edge["target"] not in node_ids:
        errors.append(f"Edge target '{edge['target']}' not found in nodes")
    if edge["source"] == edge["target"]:
        errors.append(f"Self-loop: {edge['source']}")

    return errors
