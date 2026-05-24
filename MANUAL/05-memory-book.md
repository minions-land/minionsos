# 05 — Book (L2 compiled knowledge)

> **L2 card.** The Book is durable, citation-shaped knowledge. Pages live at `branches/shared/book/sources/<role>-<slug>.md`. **Noter writes; everyone reads.**
> Top three: `mos_book_query`, `mos_book_hot_get`, and (for Noter) `mos_book_ingest`.
> The Book is the single source of truth Writer reaches for at paper-writing time.

---

## mos_book_query (everyone)

```python
args:
  query: str             # natural language; matched against page titles + content
  max_results: int = 10
  filter_role: str | None
returns: { pages: [ { slug, title, snippet, role, reel_ref?, links_in, links_out } ] }
```

Use this BEFORE you ingest a new page. If a page already covers your topic, link to it via `mos_book_save_synthesis` instead of duplicating.

---

## mos_book_hot_get (everyone)

```python
returns: {
  hot_md: str,                         # the rolling ~500-word cache
  recent_ingests: [...],
  recently_verified: [...],
  unresolved_contradictions: int,
  active_hypotheses: int,
}
```

`book/hot.md` is auto-injected at every role wake-up — but you can re-read it on demand if you want a refresher mid-cycle.

---

## mos_book_ingest (Noter only)

Promote a settled artifact (a handoff, an experiment summary, an audit) into the Book.

```python
args:
  source_path: str         # absolute path under branches/shared/
  role: str                # who originated the source
  slug: str                # short kebab-case
  title: str
  body: str | None         # if omitted, derived from source_path
  links_to: list[str]      # other slugs this references
  reel_ref: str | None     # auto-set from session env
returns: { page_path, slug, links_resolved }
```

**Pitfall (PITFALLS § P-14):** if you create a page with no `links_to`, `mos_book_lint` will keep flagging it as `ORPHAN_PAGE`. Either add a link or accept the lint warning.

---

## mos_book_ingest_batch (Noter only)

Same shape, batched. Use when ingesting an entire phase's handoffs in one wake.

---

## mos_book_save_synthesis (Noter only)

Cross-link sources into a synthesis page (no new claims, just structure).

```python
args:
  slug: str
  title: str
  body: str
  links_to: list[str]      # MUST be non-empty; this is the whole point
returns: { synthesis_page_path }
```

---

## mos_book_audit_walk (Ethics / Noter)

```python
args:
  start_slug: str | None
  max_depth: int = 5
returns: {
  isolated_pages: [...],     # no inbound links
  bridge_pages: [...],       # high betweenness
  contradictions: [...],     # detected by claim-pair walk
}
```

Use this monthly-equivalent during long projects. Bridge pages are candidates for synthesis.

---

## mos_book_resolve_contradiction (Ethics)

```python
args:
  slug: str                          # e.g. "coder-p3-width-falsifier-cgrok-h-fails"
  verdict: str                       # "resolved" | "needs-experiment" | "lexical-FP"
  rationale: str                     # MUST be specific; one-line generic = FAIL
  auditor_role: str
returns: { verdict_path, contradiction_state }
```

**Hard rule (from PITFALLS § P-6):** never accept a subagent's verdict on > 3 contradictions in one shot without checking its reel. project_37596's ethics caught a subagent stamping "Substantive disagreement requires further investigation. Close as resolved." (contradictory) on every item.

---

## mos_book_lint (Noter)

```python
returns: { warnings: [...], errors: [...] }
```
Cheap. Run after every batch ingest. Warnings:
- `ORPHAN_PAGE` — no inbound link
- `BROKEN_WIKILINK` — `[[slug]]` to non-existent page
- `MISSING_REEL_REF` — page was ingested by an EACN role with no session env

---

## mos_book_promote_verified (Noter)

```python
args:
  min_age_days: float = 7.0
  min_supporting_edges: int = 2
  max_promotions: int = 5
returns: { promoted: [...], skipped: [...] }
```

Promotes Draft nodes (type ∈ {insight, method, result}) that:
- reached `support_status=verified`
- have ≥ `min_supporting_edges` `supports` edges in the Draft
- are ≥ `min_age_days` old
- aren't already cited by a Book page

Default thresholds are conservative on purpose. Don't lower them to push your hypothesis through.

---

## mos_book_crystallize_session (Noter)

Compact one role's session activity (Draft nodes + handoffs in a window) into a single Book page.

```python
args:
  role: str
  since_iso: str
  until_iso: str | None
  slug_hint: str | None
returns: { crystallized_page, sources_consumed }
```

Use this when a role finished a phase. The page becomes the role's narrative anchor for that phase.

---

## mos_book_hot_update (Noter)

Re-render `book/hot.md`.

```python
args:
  recent_ingests: list[ { slug, title, role } ] | None
  active_hypotheses: int = 0
  recently_verified: list[str] | None
  recently_refuted: list[str] | None
  unresolved_contradictions: int = 0
returns: { hot_md_path, hash }
```

**Pitfall (PITFALLS § P-1):** project_37596's noter looped for ~10 minutes on this because the schema was deferred. Run `ToolSearch(query="select:mos_book_hot_update")` once per session before calling.
