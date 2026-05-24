# 13 — Cross-project bridge (Gru only)

> **L2 card.** Cross-project visibility is **strictly Gru-only**. Roles inside a project see nothing of any other project. Gru relays digested results.
> Top tool: `mos_project_bridge`.

---

## mos_project_bridge

```python
args:
  source_port: int            # the project Gru reading from (must be one Gru manages)
  target_port: int            # the project to read from
  query: str                  # natural-language ask
  scope: list[str] | None     # subset: ["events","artifacts","draft","book","shelf","issues"]
  since_iso: str | None
returns: {
  digest: str,                # human-readable summary
  citations: [ { project, kind, path|event_id } ],
}
```

**Behaviour.**
- Read-only across projects.
- Digests rather than dumps. Gru writes the digest into the source project's Draft / handoffs as a regular artifact for that project's roles to consume.
- Citations carry the cross-project path so an auditor can SSH in and verify.

**Hard rules (PITFALLS / project memory):**
- **Roles never bridge directly.** A role wanting cross-project data must DM Gru.
- **Bridges are append-only audit events.** Each call writes to `branches/shared/governance/bridges.jsonl`.
- **No write across projects.** A bridge cannot create a task, send a message, or publish into the target project.

---

## Patterns

### Gru cross-checks if another project hit the same bug

```python
result = mos_project_bridge(
  source_port=37596,
  target_port=22045,
  query="Did this project see the {project_workspace} dead-launch FP?",
  scope=["issues","draft"],
)
# Then digest into the source project's handoff for Coder to read
mos_publish_to_shared(role="gru", src_path=result["digest_path"],
  dst_subpath="handoffs/gru-bridge-22045-deadlaunch.md", commit_message=...)
```

### Gru pulls a cross-project related-work primer

```python
mos_project_bridge(
  source_port=37596,
  target_port=18002,                    # earlier project that wrote the V1 paper
  query="Summarise V1's Section 3 narrative on grokking critical norm",
  scope=["book"],
)
```

---

## Pitfalls

- **Don't bridge during a hot session.** Bridges read across SQLite files; they're cheap but block on locks if the target project is mid-write.
- **Don't paraphrase citations away.** Always carry the citation list into the digest you publish — Roles in the source project will look at the citation paths to validate.
- **Bridges expire.** Cross-project state changes after the bridge runs. If a downstream Role acts on a stale digest > 1 hour old, re-bridge.
