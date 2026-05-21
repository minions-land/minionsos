"""Unit tests for minions.identity — Ed25519-ready identity layer."""

from __future__ import annotations

from pathlib import Path

import pytest

from minions import identity


@pytest.fixture(autouse=True)
def _isolated_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MINIONS_IDENTITY_DIR", str(tmp_path / "identity"))
    monkeypatch.setenv("MINIONS_PROJECT_PORT", "9999")


class TestGenerateIdentity:
    def test_generates_seed_and_fingerprint(self, tmp_path: Path):
        result = identity.generate_identity()
        assert result["created"] is True
        assert len(result["fingerprint"]) == 16
        d = Path(result["identity_dir"])
        assert (d / "seed.key").exists()
        assert (d / "fingerprint.pub").exists()
        assert (d / "meta.json").exists()

    def test_idempotent_without_force(self):
        first = identity.generate_identity()
        second = identity.generate_identity()
        assert second["created"] is False
        assert second["fingerprint"] == first["fingerprint"]

    def test_force_regenerates(self):
        first = identity.generate_identity()
        second = identity.generate_identity(force=True)
        assert second["created"] is True
        # New seed → (almost certainly) new fingerprint.
        # Collision probability is 2^-64, safe to assert inequality.
        assert second["fingerprint"] != first["fingerprint"]

    def test_seed_file_permissions(self, tmp_path: Path):
        identity.generate_identity()
        seed_path = Path(identity._identity_dir()) / "seed.key"
        mode = seed_path.stat().st_mode & 0o777
        assert mode == 0o600


class TestLoadFingerprint:
    def test_raises_when_no_identity(self):
        with pytest.raises(RuntimeError, match="identity not found"):
            identity.load_fingerprint()

    def test_returns_fingerprint_after_generate(self):
        identity.generate_identity()
        fp = identity.load_fingerprint()
        assert len(fp) == 16
        assert all(c in "0123456789abcdef" for c in fp)


class TestProjectFingerprint:
    def test_deterministic_for_same_port(self):
        identity.generate_identity()
        fp1 = identity.project_fingerprint(9999)
        fp2 = identity.project_fingerprint(9999)
        assert fp1 == fp2
        assert len(fp1) == 16

    def test_different_ports_different_fingerprints(self):
        identity.generate_identity()
        fp1 = identity.project_fingerprint(9999)
        fp2 = identity.project_fingerprint(10000)
        assert fp1 != fp2


class TestMakeUid:
    def test_format(self):
        identity.generate_identity()
        uid = identity.make_uid(port=9999, content_type="draft", slug="H-042")
        assert uid.startswith("mos://")
        parts = uid.split("/")
        assert len(parts) == 6  # mos: // owner / project / type / slug
        assert parts[4] == "draft"
        assert parts[5] == "H-042"

    def test_stable_across_calls(self):
        identity.generate_identity()
        uid1 = identity.make_uid(port=9999, content_type="chapter", slug="findings")
        uid2 = identity.make_uid(port=9999, content_type="chapter", slug="findings")
        assert uid1 == uid2

    def test_different_slugs_different_uids(self):
        identity.generate_identity()
        uid1 = identity.make_uid(port=9999, content_type="chapter", slug="a")
        uid2 = identity.make_uid(port=9999, content_type="chapter", slug="b")
        assert uid1 != uid2


class TestParseUid:
    def test_roundtrip(self):
        identity.generate_identity()
        uid = identity.make_uid(port=9999, content_type="dead-end", slug="failed-approach")
        parsed = identity.parse_uid(uid)
        assert parsed is not None
        assert parsed["content_type"] == "dead-end"
        assert parsed["slug"] == "failed-approach"
        assert parsed["owner"] == identity.load_fingerprint()
        assert parsed["project"] == identity.project_fingerprint(9999)

    def test_malformed_returns_none(self):
        assert identity.parse_uid("not-a-uid") is None
        assert identity.parse_uid("mos://only/two") is None

    def test_uid_is_local(self):
        identity.generate_identity()
        uid = identity.make_uid(port=9999, content_type="draft", slug="x")
        assert identity.uid_is_local(uid) is True
        assert identity.uid_is_local("mos://deadbeef12345678/abcd/draft/x") is False


class TestRelativeId:
    def test_resolve_rid_found(self):
        refs = {"attention-theory": "mos://aaa/bbb/chapter/attention-theory"}
        assert identity.resolve_rid("[attention-theory]", refs) == refs["attention-theory"]

    def test_resolve_rid_not_found(self):
        assert identity.resolve_rid("[missing]", {}) is None

    def test_build_references_entry(self):
        entry = identity.build_references_entry("my-slug", "mos://a/b/c/d")
        assert entry == {"my-slug": "mos://a/b/c/d"}
