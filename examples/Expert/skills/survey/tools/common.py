"""
ModernKnowledge — common.py
Shared utilities for multi-topic support.
"""

import argparse
import os
from pathlib import Path

TOOLS_DIR = Path(__file__).parent
SKILL_ROOT = TOOLS_DIR.parent
SCHEMA_PATH = SKILL_ROOT / "schema" / "schema.yaml"

# Topics live under the user's working directory, not inside the skill
TOPICS_DIR = Path(os.environ.get("MK_TOPICS_DIR", Path.cwd() / "surveys" / "topics"))


def resolve_topic(topic: str) -> Path:
    """Resolve a topic name to its directory under topics/."""
    d = TOPICS_DIR / topic
    if not d.exists():
        raise FileNotFoundError(f"Topic '{topic}' not found at {d}")
    return d


def list_topics() -> list[str]:
    """List all available topics."""
    if not TOPICS_DIR.exists():
        return []
    return sorted(d.name for d in TOPICS_DIR.iterdir() if d.is_dir())


def add_topic_arg(parser: argparse.ArgumentParser):
    """Add --topic argument to a parser."""
    topics = list_topics()
    default = topics[0] if len(topics) == 1 else None
    parser.add_argument(
        "--topic", required=(default is None), default=default,
        help=f"Topic name. Available: {', '.join(topics) or '(none)'}",
    )


def init_topic(topic: str) -> Path:
    """Create a new topic directory with the standard structure."""
    d = TOPICS_DIR / topic
    for sub in ["nodes/paradigms", "nodes/directions", "nodes/methods",
                "nodes/components", "nodes/claims", "nodes/evidence",
                "papers", "reports", "extractions", "candidates"]:
        (d / sub).mkdir(parents=True, exist_ok=True)
    return d
