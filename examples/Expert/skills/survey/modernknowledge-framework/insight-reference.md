# Nine Insight Types (pure topology, no LLM)

Produced by `tools/insights.py` from `lattice.json`. Use these as the structural spine of the final survey narrative.

| # | Insight | Source edges/fields | What it surfaces |
|---|---------|---------------------|------------------|
| 1 | 🧬 Evolution Spine | `extends` / `supersedes` chains | Canonical lineage of a method family |
| 2 | 🌊 Convergence Funnel | `converges_with`, shared components | Directions merging into a common paradigm |
| 3 | ⚔️ Claim Conflict | `contradicts` / `refines` between claims | Open controversies |
| 4 | 🏝️ Orphan Innovation | Methods with few/no outgoing `extends` | Genuinely novel ideas not yet absorbed |
| 5 | 🛠️ Component Hub | Component `used_by` high in-degree | Load-bearing reusable parts |
| 6 | 🌿 Branching Burst | `branches_from` clusters | Fragmentation of a direction |
| 7 | ❓ Open Problem | Claims with many `refines` but no resolution | Unsettled questions |
| 8 | 📏 Applicability Boundary | Method `constraints` | Where a method breaks |
| 9 | 🔀 Cross-Field Transfer | `transfers_from` + `origin_field` | Ideas imported from other fields |

## Recommended narrative mapping

- **Vertical survey** → feeds Insights 1, 5, 8 (lineage, components, constraints)
- **Horizontal survey** → feeds Insights 2, 6, 9 (convergence, branching, transfer)
- **Reviewer** → feeds Insights 3, 4, 7 (conflict, orphans, open problems)

A final survey becomes strongest when each of the 9 insight types has at least one concrete entry with a source citation.
