"""MinionsOS identity layer — per-install stable identity + Universal ID generation.

Every MinionsOS installation has a stable identity stored at
``~/.minionsos/identity/``. The identity is generated once at install time
and never changes. It provides:

1. A 256-bit secret seed (``seed.key``) — kept private, never shared.
2. A public fingerprint derived from the seed (``fingerprint.pub``) — the
   owner component of every Universal ID this installation produces.
3. UID generation for Draft nodes, Book chapters, and other knowledge units.

The fingerprint is the first 16 hex characters (8 bytes) of
BLAKE2b(seed, digest_size=20). This gives 64 bits of collision resistance
which is sufficient for a federated knowledge network (birthday bound at
~4 billion installs).

Future work (PR-4): replace the seed with an Ed25519 keypair so the
fingerprint doubles as a verifiable public key. The UID format is designed
to be forward-compatible with that change — the fingerprint slot is the
same length regardless of whether it comes from a raw seed or a pubkey.

Environment:
    MINIONS_IDENTITY_DIR — override identity storage location (testing).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
from pathlib import Path

logger = logging.getLogger(__name__)

_IDENTITY_DIR_ENV = "MINIONS_IDENTITY_DIR"
_DEFAULT_IDENTITY_DIR = Path.home() / ".minionsos" / "identity"
_SEED_FILE = "seed.key"
_FINGERPRINT_FILE = "fingerprint.pub"
_META_FILE = "meta.json"
_FINGERPRINT_HEX_LEN = 16  # 8 bytes = 16 hex chars


def _identity_dir() -> Path:
    env = os.environ.get(_IDENTITY_DIR_ENV, "").strip()
    return Path(env) if env else _DEFAULT_IDENTITY_DIR


def _generate_seed() -> bytes:
    return secrets.token_bytes(32)


def _derive_fingerprint(seed: bytes) -> str:
    digest = hashlib.blake2b(seed, digest_size=20).hexdigest()
    return digest[:_FINGERPRINT_HEX_LEN]


def identity_exists() -> bool:
    """True if this installation already has a generated identity."""
    d = _identity_dir()
    return (d / _SEED_FILE).exists() and (d / _FINGERPRINT_FILE).exists()


def generate_identity(*, force: bool = False) -> dict[str, str | bool]:
    """Generate a new installation identity. Idempotent unless force=True.

    Returns {"fingerprint": "...", "identity_dir": "...", "created": bool}.
    """
    d = _identity_dir()
    if identity_exists() and not force:
        fp = (d / _FINGERPRINT_FILE).read_text(encoding="utf-8").strip()
        return {"fingerprint": fp, "identity_dir": str(d), "created": False}

    d.mkdir(parents=True, exist_ok=True)
    seed = _generate_seed()
    fingerprint = _derive_fingerprint(seed)

    seed_path = d / _SEED_FILE
    seed_path.write_bytes(seed)
    seed_path.chmod(0o600)

    (d / _FINGERPRINT_FILE).write_text(fingerprint + "\n", encoding="utf-8")
    (d / _META_FILE).write_text(
        json.dumps(
            {
                "version": 1,
                "fingerprint_algo": "blake2b-160-trunc8",
                "seed_bytes": 32,
                "note": "Ed25519 upgrade planned for federation layer",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    logger.info("generated MinionsOS identity: fingerprint=%s dir=%s", fingerprint, d)
    return {"fingerprint": fingerprint, "identity_dir": str(d), "created": True}


def load_fingerprint() -> str:
    """Load the owner fingerprint. Raises if identity not yet generated."""
    d = _identity_dir()
    fp_path = d / _FINGERPRINT_FILE
    if not fp_path.exists():
        raise RuntimeError(
            f"MinionsOS identity not found at {d}. Run ./install.sh or "
            "call minions.identity.generate_identity() first."
        )
    return fp_path.read_text(encoding="utf-8").strip()


# ---------------------------------------------------------------------------
# Project fingerprint
# ---------------------------------------------------------------------------


def project_fingerprint(port: int) -> str:
    """Derive a stable project fingerprint from its port + creation metadata.

    The fingerprint is deterministic for a given project: same port on the
    same installation always produces the same fingerprint. This is used as
    the {project} component of Universal IDs.

    Uses BLAKE2b(owner_fingerprint + port bytes, digest_size=8) → 16 hex.
    """
    owner = load_fingerprint()
    data = f"{owner}:{port}".encode()
    return hashlib.blake2b(data, digest_size=8).hexdigest()


# ---------------------------------------------------------------------------
# Universal ID (UID) generation
# ---------------------------------------------------------------------------

_UID_SCHEME = "mos"


def make_uid(
    *,
    port: int,
    content_type: str,
    slug: str,
) -> str:
    """Generate a Universal ID for a knowledge unit.

    Format: mos://{owner}/{project}/{content_type}/{slug}

    Args:
        port: project port (used to derive project fingerprint).
        content_type: one of "draft", "chapter", "dead-end", "book".
        slug: human-readable identifier within the content type.

    Returns:
        A globally unique, stable UID string.
    """
    owner = load_fingerprint()
    project = project_fingerprint(port)
    return f"{_UID_SCHEME}://{owner}/{project}/{content_type}/{slug}"


def parse_uid(uid: str) -> dict[str, str] | None:
    """Parse a UID into its components. Returns None if malformed."""
    if not uid.startswith(f"{_UID_SCHEME}://"):
        return None
    rest = uid[len(f"{_UID_SCHEME}://") :]
    parts = rest.split("/", 3)
    if len(parts) != 4:
        return None
    return {
        "owner": parts[0],
        "project": parts[1],
        "content_type": parts[2],
        "slug": parts[3],
    }


def uid_owner(uid: str) -> str | None:
    """Extract the owner fingerprint from a UID."""
    parsed = parse_uid(uid)
    return parsed["owner"] if parsed else None


def uid_is_local(uid: str) -> bool:
    """True if this UID was generated by the current installation."""
    parsed = parse_uid(uid)
    if not parsed:
        return False
    try:
        return parsed["owner"] == load_fingerprint()
    except RuntimeError:
        return False


# ---------------------------------------------------------------------------
# Relative ID (RID) resolution
# ---------------------------------------------------------------------------


def resolve_rid(
    rid: str,
    references: dict[str, str],
) -> str | None:
    """Resolve a Relative ID to a Universal ID using a references mapping.

    RID forms:
        [slug]                      → lookup in references
        [project-slug/slug]         → lookup with project prefix
        [@owner-alias/project/slug] → lookup with full path

    Returns the UID string or None if not found.
    """
    clean = rid.strip("[]")
    return references.get(clean)


def build_references_entry(rid: str, uid: str) -> dict[str, str]:
    """Create a single references.json entry."""
    return {rid: uid}
