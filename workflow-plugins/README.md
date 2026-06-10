# Workflow Plugins

Pluggable external workflows that integrate into MinionsOS as on-demand Expert
instances. Each workflow plugin is spawned as an independent `expert-{slug}` with
full EACN3 participation but a sovereign output boundary.

## Recommended approach: repo-level workflows

The recommended way to add an external workflow is **repo-level**: clone the
workflow's repository into the workflow plugin directory, point the manifest at its
MCP server entry point, and let the Expert drive it through MCP tools.

This approach works because most modern agent workflows already ship as:
- A git repo with runnable code
- An MCP server (or can be wrapped as one)
- Skills / prompts / agents defined as markdown

MinionsOS doesn't reinvent these — it mounts them as-is and lets an Expert
operate them within the EACN3 coordination fabric.

### How to add a repo-level workflow

```bash
# 1. Create the workflow plugin directory
mkdir -p workflow-plugins/{slug}/skills

# 2. Clone the workflow repo (gitignored — not tracked in MinionsOS)
cd workflow-plugins/{slug}
echo "repo/" > .gitignore
git clone --depth=1 https://github.com/org/workflow.git repo

# 3. Build the MCP server (if needed)
cd repo && npm install && npm run build

# 4. Write manifest.yaml pointing at the built server
# 5. Write domain.md summarizing what this workflow does
# 6. Write skills/*.md with procedures for the Expert to follow
```

See `workflow-plugins/evoany/` for a complete worked example.

## Directory layout

```
workflow-plugins/{slug}/
├── manifest.yaml       # required — declares capabilities
├── .gitignore          # typically ignores repo/ (cloned at setup time)
├── setup.sh            # optional — idempotent clone + build script
├── domain.md           # optional — injected into Expert system prompt
├── skills/             # optional — *.md procedure files rendered as Skill bundles
│   └── *.md
└── repo/               # the external workflow repo (gitignored)
    └── ...
```

## Manifest format

```yaml
name: evoany
description: "EvoAny — evolutionary code optimization engine"
version: "0.1.0"

# MCP server from the cloned repo
mcp_server:
  command: "node"
  args: ["workflow-plugins/evoany/repo/dist/plugin/server.js"]
  env: {}
  tools:
    - evo_init
    - evo_step
    - evo_get_status

# Domain context appended to Expert system prompt
domain_pack: "domain.md"

# Extra EACN discovery domains
eacn_domains:
  - "evolutionary-optimization"
  - "code-evolution"
```

### Manifest fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | yes | Human-readable name |
| `description` | yes | One-line summary |
| `version` | no | Semver string (default "0.1.0") |
| `mcp_server` | no | MCP server spec: `command`, `args`, `env`, `tools[]` |
| `domain_pack` | no | Relative path to domain context markdown |
| `eacn_domains` | no | Extra EACN3 discovery domains for the Expert |

## Usage

```python
# Gru discovers available workflow plugins
mos_list_workflow_plugins()
# → [{"slug": "evoany", "name": "evoany", "has_mcp": true, ...}]

# Gru spawns an Expert with the workflow plugin attached
mos_spawn_expert(
    project_port=37596,
    domain="evolutionary-optimization",
    workflow_plugin="evoany",
    init_brief="Use EvoAny to optimize the training loop in src/train.py"
)
```

The spawned Expert gets:
- Its own branch (`branches/expert-{slug}/`)
- The workflow plugin's MCP server in a per-instance config (not global `.mcp.json`)
- The workflow plugin's `domain.md` appended to its system prompt
- The workflow plugin's `skills/*.md` rendered into
  `.claude/skills/workflow-plugin-{slug}-{skill}/SKILL.md` inside that
  branch workspace
- Full EACN3 participation (messages, tasks, bids — not just Gru DM)

## Boundaries

- Workflow plugin Experts write only to their own branch
- Cross-role output goes through `mos_publish_to_shared` → `handoffs/` only
- They do NOT write to `draft/`, `notes/`, `book/`, or other native surfaces
- MinionsOS's own Scientific Discovery workflow is sovereign — workflow plugins
  provide capabilities but never replace or overwrite the native system
- Dismiss removes the process; no explicit MCP unload needed

## Lifecycle

```
setup.sh          → clone + build (one-time, or on update)
mos_spawn_expert  → Expert process starts with workflow plugin context
  ... Expert drives the workflow via MCP tools ...
  ... Expert reports results via EACN3 ...
mos_dismiss_role  → process dies, MCP server dies with it
```

## Compatibility guide

The workflow-plugin architecture is designed to absorb the major categories of
scientific agent workflows. Below is how each category maps to a workflow plugin.

### Category 1: End-to-end research pipelines

Systems that take a research question and return a draft paper or reproducible
artifact. They typically have their own multi-agent orchestration internally.

| System | Integration pattern |
|--------|-------------------|
| [AI Scientist](https://github.com/SakanaAI/AI-Scientist) | MCP wrapper around its pipeline stages; Expert drives idea→experiment→write→review |
| [gpt-researcher](https://github.com/assafelovic/gpt-researcher) | Already has an API; wrap as MCP server, Expert calls research/report endpoints |
| [Agent Laboratory](https://github.com/SamuelSchmidgall/AgentLaboratory) | Mount its agent orchestrator; Expert delegates sub-tasks through its internal agents |
| [AI-Researcher (HKU)](https://github.com/HKUDS/AI-Researcher) | Same pattern as AI Scientist — wrap pipeline stages as MCP tools |
| [EvoAny](https://github.com/DataLab-atom/EvoAny) | Already ships MCP server — mount directly (see `workflow-plugins/evoany/`) |

**Key principle**: the external pipeline's internal agents are invisible to
EACN3. The workflow-plugin Expert is the single point of contact. It drives the
pipeline and reports results back to the team.

### Category 2: Skill collections (static)

Repositories of markdown skills, prompts, and procedures. No runtime server.

| Collection | Integration pattern |
|-----------|-------------------|
| [K-Dense/scientific-agent-skills](https://github.com/K-Dense-AI/scientific-agent-skills) | Copy relevant skills into `skills/`; write `domain.md` summarizing the collection |
| [Orchestra-Research/AI-Research-SKILLs](https://github.com/Orchestra-Research/AI-Research-SKILLs) | Same — select skills by category, inject as Expert procedures |
| [academic-research-skills](https://github.com/Imbad0202/academic-research-skills) | Four-skill pipeline → four files in `skills/` |
| [nature-skills](https://github.com/Yuan1z0825/nature-skills) | Six Nature-style skills → `skills/` + domain.md with house-style rules |
| [claude-scholar](https://github.com/Galaxy-Dawn/claude-scholar) | Skills + Zotero MCP integration → `skills/` + MCP server for Zotero |
| [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) | Engineering methodology → `skills/` for lifecycle commands |

**Key principle**: no MCP server needed. The value is in `domain.md` (context)
and `skills/*.md` (procedures). At spawn time MinionsOS turns each procedure
file into a project-local Claude Code bundle in the spawned Expert's branch
workspace. Tool access still comes from the Expert's existing tool surface;
the source file's prose does not grant extra tools.

### Category 3: Structured artifact protocols

Systems that define how research outputs should be structured (not how to
produce them). These integrate as domain packs + skills, not as MCP servers.

| Protocol | Integration pattern |
|----------|-------------------|
| [ARA (Agent-Native Research Artifact)](https://github.com/Orchestra-Research/Agent-Native-Research-Artifact) | `domain.md` describes the four-layer layout; `skills/` has compiler, research-manager, rigor-reviewer procedures |
| [SSL (Structured Skill Language)](https://github.com/COOLPKU/SSL) | Scheduling/structural/logical decomposition → `domain.md` for the Expert's own skill management |

### Category 4: Memory and knowledge systems

Systems that provide long-term memory, knowledge graphs, or retrieval. These
integrate as MCP servers that the Expert can query.

| System | Integration pattern |
|--------|-------------------|
| [Claude-Mem](https://github.com/thedotmack/claude-mem) | MCP server for session memory — mount directly |
| [Mem0](https://docs.mem0.ai) | MCP wrapper around its API; Expert stores/retrieves cross-session knowledge |
| [Zep](https://help.getzep.com) | Same — temporal knowledge graph as MCP |
| [Letta](https://docs.letta.com) | Stateful agent memory as MCP |

**Key principle**: memory MCP servers complement MinionsOS's native Book (L2)
and Draft (L1). The Expert uses them for its own recall; promotion into the
project's shared surfaces still goes through `mos_publish_to_shared`.

### Category 5: Multi-agent writing workflows

Systems where multiple agents collaborate on paper writing with role
separation (PI, reviewer, authoring agent, statistician, etc.).

| System | Integration pattern |
|--------|-------------------|
| [AutoSurvey](https://arxiv.org/abs/2406.10252) | Wrap its four-stage survey pipeline as MCP tools |
| [GPT Academic](https://github.com/binary-husky/gpt_academic) | Wrap its paper-processing functions as MCP |
| [RebuttalStudio](https://github.com/Imbad0202/academic-research-skills) | Skills-only — procedures for rebuttal writing |

**Key principle**: if the external system has its own multi-agent orchestration,
wrap it as a single MCP surface. The workflow-plugin Expert is the coordinator
visible to MinionsOS; internal agents are implementation details.

### Writing your own integration

For any workflow not listed above, the pattern is:

1. **Does it have a runnable API/CLI?** → Wrap as MCP server, mount in manifest
2. **Is it just prompts/procedures?** → Put markdown source files in `skills/` and context in `domain.md`
3. **Is it both?** → MCP for the runtime, skills for the procedures
4. **Does it need persistent state?** → Its state lives in `repo/` or its own
   database; the Expert's branch is for MinionsOS-facing outputs only

## Examples

- `workflow-plugins/evoany/` — EvoAny evolutionary code optimization
  (https://github.com/DataLab-atom/EvoAny)
