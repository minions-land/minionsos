# Stage B Coherence — common/eacn3-* cluster A (7 skills)

Scope: tool-reference manuals for the first half of the `eacn3-*` cluster.
Coherence rubric: tightly-scoped tool cluster, trigger up front, tool-index +
per-tool subsections, failure paths inline, cross-refs not duplication.

## Bucket summary

| Skill | Bucket | Confidence |
|---|---|---|
| eacn3-agent-lifecycle | COHERENT | high |
| eacn3-bootstrap | COHERENT | high |
| eacn3-discovery | COHERENT | high |
| eacn3-economy | COHERENT | high |
| eacn3-error-recovery | COHERENT | high |
| eacn3-event-loop | NEEDS POLISH | medium |
| eacn3-messaging | COHERENT | high |

Counts: 6 COHERENT, 1 NEEDS POLISH, 0 NEEDS REWRITE, 0 STITCHED-TOGETHER.

## Per-skill verdicts

### eacn3-agent-lifecycle — COHERENT
**Evidence:**
- Frontmatter `tools:` lists exactly the five identity-management tools, and
  the body opens with: "Five tools that create and manage Agent identities
  attached to your Server."
- "When to invoke" disambiguates host vs standalone: "In MinionsOS, Agent
  identities are pre-registered by the host runtime ... do not call
  `eacn3_register_agent` or `eacn3_unregister_agent`."

**Diagnosis:** One scoped cluster (identity CRUD + listing), strong
"when to invoke" with MinionsOS-vs-standalone branching, ASCII diagram of the
identity-creation graph, per-tool subsections with inputs / outputs / side
effects, pitfalls inline. The `eacn3_claim_agent` overlap with `eacn3-bootstrap`
is handled by an explicit cross-reference ("documented in `eacn3-bootstrap` —
it lives on the session boundary rather than the identity-creation boundary"),
not duplication.

**Action:** None.

### eacn3-bootstrap — COHERENT
**Evidence:**
- "The seven tools that bring a Server session online, keep it alive, inspect
  its state, and bring it down again, plus the call that resumes a previously-
  registered Agent identity."
- "In MinionsOS, the host runtime already manages the Server session — the
  only call you normally need from this cluster is `eacn3_health` for
  diagnostics."

**Diagnosis:** Three-layer ASCII grouping (Diagnostics / Session lifecycle /
Identity reuse) is honest about the scope; `eacn3_claim_agent` is in the
"Identity reuse" pane, which justifies its presence here despite being
identity-flavored. MinionsOS-specific guidance is fenced inside "When to
invoke" rather than leaking into per-tool sections. Pitfalls cover the
non-obvious cases (disconnect cascades, fallback hint, single-Server
constraint).

**Action:** None.

### eacn3-discovery — COHERENT
**Evidence:**
- "Two tools for finding Agents on the network: a gossip-first discovery that
  matches how real collaborators spread, and a flat registry browse that
  paginates every indexed Agent."
- A "Choosing between them" table maps intent → tool.

**Diagnosis:** Smallest scope of the cluster (2 tools), clearest framing.
ASCII diagram contrasts the two access patterns. No duplication with
`eacn3-agent-lifecycle` (creation) or `eacn3-task-queries` (task-side reads).

**Action:** None.

### eacn3-economy — COHERENT
**Evidence:**
- "Two tools for the account substrate: read a balance, add credits."
- Lifecycle bullet list ties `eacn3_create_task / eacn3_confirm_budget /
  eacn3_select_result / eacn3_close_task` to balance transitions, with
  cross-references rather than re-documenting those tools.

**Diagnosis:** Tight 2-tool scope with the account-model ASCII diagram, the
escrow lifecycle as a referenced summary, per-tool details, and well-targeted
pitfalls (frozen-as-spendable, fee accounting, "deposit is not payment").

**Action:** None.

### eacn3-error-recovery — COHERENT
**Evidence:**
- Scope fence: "Covers the network / transport / plugin failure surface, not
  the protocol surface — for `400 Cannot collect results in status X` and
  similar, see `eacn3-state-machines`."
- Three failure classes (Transport / Network / Plugin) with distinct recovery
  branches and a MinionsOS-vs-standalone split inside the Plugin branch.

**Diagnosis:** Procedural skill rather than tool-reference; the four tools in
the frontmatter (`eacn3_health`, `eacn3_cluster_status`, `eacn3_server_info`,
`eacn3_get_task`) are precisely the ones used in the recovery procedure, and
the skill correctly defers identity tools to lifecycle and FSM errors to
state-machines. The "Recovery is bounded" rule and the `eacn3_get_task`
reconciliation step are this skill's unique contribution, not duplicated
elsewhere.

**Action:** Minor — frontmatter `references:` lists
`eacn-network-collaboration` (note the missing `3`); no skill by that name
exists in this library. Likely intended `eacn3-network-overview`. Worth
fixing on the next pass.

### eacn3-event-loop — NEEDS POLISH
**Evidence:**
- Title-line scope creep: "the three draining tools, the reverse-control
  diagnostic, and the event taxonomy that drives every reactive workflow."
- `eacn3_reverse_control_status` lives next to the queue drainers, but its own
  body says it inspects "the MCP reverse-control engine — the subsystem that
  lets EACN3 proactively drive a connected Agent via sampling requests and
  notifications."

**Diagnosis:** Two things are bundled. (1) The three queue-drain tools
(`get_events` / `await_events` / `next`) plus the event taxonomy form one
clean cluster — that part is excellent, with a comparison diagram, per-tool
sections, choose-between block, and a unified "common sequence" recipe.
(2) `eacn3_reverse_control_status` is a different surface (sampling /
notifications subsystem); it shares only the loose theme of "events come into
the agent." Splicing it in makes the skill's scope drift from "drain my
queue" to "anything event-shaped."

The MinionsOS-vs-standalone fencing is correct and consistent with
`error-recovery` ("scheduler outside the agent already chains
`GET /api/events/{agent_id}` long-polls").

**Action:** Move `eacn3_reverse_control_status` into either a small
`eacn3-reverse-control` skill or fold it into `eacn3-agent-lifecycle` (since
reverse-control is configured in `eacn3_register_agent`). Then the event-loop
skill becomes a clean 3-tool drain cluster + taxonomy. If a split is too
heavy, at minimum re-frame the section header to acknowledge the orthogonal
surface ("Sampling / reverse-control diagnostic — not part of queue draining,
covered here only because the same plugin owns it").

### eacn3-messaging — COHERENT
**Evidence:**
- "Three tools for direct agent-to-agent communication outside the task
  market: send a message, read history with one peer, list every peer you
  have a session with."
- Delivery-method ASCII diagram (`local → a2a_direct → relay`) is unique to
  this skill; cross-refs the `direct_message` event taxonomy to
  `eacn3-event-loop` rather than re-explaining.

**Diagnosis:** Tight 3-tool scope. The "use tasks for substantive work"
fencing is in both "When to invoke" and the pitfalls, which is a deliberate
emphasis rather than duplication. History-cap and per-session locality are
called out as gotchas.

**Action:** None.

## Cross-skill issues

- **Broken reference (low impact).** `eacn3-error-recovery` frontmatter
  references `eacn-network-collaboration`, which does not exist in this
  library. The intended target is almost certainly `eacn3-network-overview`.
- **`eacn3_claim_agent` documentation site.** `eacn3-bootstrap` documents
  `claim_agent` in detail; `eacn3-agent-lifecycle` mentions it once and
  defers to bootstrap. This is the *intentional* split (session boundary vs
  identity-creation boundary) and both files cite each other consistently.
  No fix needed; flagged so a future editor does not "consolidate" them.
- **Reverse-control split-brain.** `eacn3-agent-lifecycle` documents the
  `reverse_control` block as a registration option; `eacn3-event-loop`
  documents `eacn3_reverse_control_status` as a queue-adjacent diagnostic.
  An agent debugging "why is sampling not firing?" has to read both. See the
  event-loop action above.
- **MinionsOS host-drains-the-queue rule.** Stated in three places:
  `eacn3-event-loop` (Pitfalls: "Double-draining"), `eacn3-error-recovery`
  (procedure step 4: "Do not try to restart yourself"), and the skill front
  matter summaries themselves. Wording is consistent across the three; this
  is reinforcement, not contradiction. Acceptable as-is for a tool-reference
  cluster targeted at both standalone and MinionsOS readers.
- **Account / escrow model.** The escrow lifecycle bullets in
  `eacn3-economy` describe the same state changes that the FSM lives in
  `eacn3-state-machines`. Economy frames it from the balance-substrate side,
  not the task-FSM side, so this is angle-difference, not duplication.
  Confirmed by checking `eacn3-network-overview` does not also re-describe
  the balance lifecycle.
- **Event-taxonomy ownership.** `eacn3-event-loop` owns the full event-type
  table; `eacn3-network-overview` only sketches "drain → act → exit." No
  drift between the two.
