# 99 — Source evidence

This appendix documents where the rules in this manual came from, so future agents can validate and extend.

## Real-project basis

All `PITFALLS.md` entries and "Real example" blocks are grounded in:

```
host:  connect.bjb2.seetacloud.com:40257
path:  /root/autodl-tmp/Grokking/project_37596
project: grokking-critical-norm-v2 (port 37596, profile=scientific-paper)
status:  dormant as of 2026-05-25
```

Roles observed in this project:
- gru
- noter (3-min timer driven; 3.8 MB log)
- coder (14 MB log; primary failure source)
- ethics (14 MB log; secondary failure source)
- expert-mathematician (9.4 MB)
- expert-dl-arch (12 MB)
- expert-theory-normalization (9.8 MB)
- (and one mis-spelled `theory-normalization-expert` that triggered the P0 boundary bug)

Issues filed: ISS-37596-1 (boundary), ISS-37596-10 (`{project_workspace}` dead-launch FP), ISS-37596-14 (FP supplementary).

## Source files referenced

When the manual cites a tool signature, the source is:

| Domain | File |
|---|---|
| Lifecycle | `minions/lifecycle/{project,role,role_launcher,agent_host}.py` |
| Project tools | `minions/tools/mcp/project_tools.py`, `spawn_tools.py` |
| Memory tools | `minions/tools/mcp/memory_tools.py` |
| Experiment tools | `minions/tools/mcp/experiment_tools.py` + `minions/tools/experiment_*.py` |
| Publish | `minions/tools/mcp/publish_tools.py` + `minions/tools/publish.py` |
| Reel | `minions/tools/mcp/reel_tools.py` |
| Visual | `minions/tools/mcp/visual_tools.py` |
| Runtime / wake | `minions/tools/mcp/runtime_tools.py` + `minions/tools/await_events.py` |
| Signboard | `minions/tools/mcp/signboard_tools.py` |
| Role evolution | `minions/tools/mcp/role_evolution_tools.py` + `minions/lifecycle/role_evolution.py` |
| Paper search | `minions/tools/mcp/paper_tools.py` + `minions/tools/paper_search.py` |
| Authz / whitelist | `minions/config/__init__.py:_SERVER_AUTHZ`, `minions/tools/whitelist.py` |
| Profiles | `minions/profiles/<name>.yaml` + `minions/profiles/__init__.py` |

## How to extend

1. **A new tool was added.** Update `INDEX.md` (one line), then add an entry to the matching chapter (`NN-*.md`). Cite the source file + a real-project example if you have one.
2. **A new failure mode was observed.** Add a `P-NN` entry to `PITFALLS.md`. Always include: symptom (with exact log line), cause, recipe.
3. **A whitelist or profile rule changed.** Update the relevant table — chapter 01 has the role table, chapter 07 has the publish whitelist, chapter 09 has the strategies.
4. **A whole new domain.** Add a new chapter; register it in `README.md`'s chapter map and in `DECISION-MAP.md` rows.

## Maintenance principles

- **Tool-book, not narrative.** Every page should be skimmable: signature, args, pitfalls, one example. No multi-paragraph explanations.
- **Real evidence > textbook.** Prefer "project_37596 logged this on 2026-05-24" over "you might encounter".
- **Three-layer disclosure stays three-layer.** L1 = README/INDEX/DECISION-MAP/PITFALLS. L2 = top of each chapter. L3 = entries inside each chapter. Don't blur the layers — agents read just enough.
- **Pitfalls cap at one page.** When `PITFALLS.md` grows past ~20 entries, split by domain.
