# MANUAL — schemas

## Atomic page (`tools/<name>.md`, `pitfalls/<id>.md`, `recipes/<id>.md`)

```yaml
---
id:        mos_exp_run                        # globally unique slug
kind:      tool | pitfall | recipe | domain
domain:    experiments                        # one of: lifecycle eacn3 experiments memory publish papers deliverables visual runtime debug bridge evolution
auth:      [coder]                            # role names that may call; ['*'] = all EACN roles
source:    minions/tools/mcp/experiment_tools.py:33   # file:line of @mcp.tool() decorator
since:     v15.0                              # earliest known version (best effort)
keywords:  [exp, run, gpu, training, ssh, local]      # for lookup matching
related:   [mos_exp_status, mos_exp_queue_submit]     # other page ids
status:    stable | deferred | gru-only       # call-time hint
---

# {{id}}

**One line:** ...

## Signature
```py
{{name}}(args) -> {{return type}}
```

## Args (only non-obvious; full schema lives in source)
- `field`: ...

## Pitfalls
- ...

## Real example (project_37596)
```py
...
```

## See also
- [[other-page-id]]
```

Length budget: 30-80 lines. Pages exceeding 80 lines must split.

## INDEX.json (built by `scripts/build_index.py`)

```jsonc
{
  "version": "<sha>",
  "built_at": "ISO",
  "pages": {
    "<id>": {
      "kind": "tool" | "pitfall" | "recipe" | "domain",
      "path": "tools/mos_exp_run.md",
      "domain": "experiments",
      "auth": ["coder"],
      "source": "minions/tools/mcp/experiment_tools.py:33",
      "summary": "One-line plain text from page body.",
      "keywords": [...],
      "related": [...]
    }
  },
  "domains": { "experiments": ["mos_exp_run", ...] },
  "by_role": { "coder": [...] },
  "by_keyword": { "queue": [...] }
}
```

## lookup.py interface

```bash
python3 MANUAL/scripts/lookup.py "queue dispatch retry"
# → top 5 page ids + first 12 lines + path
```

Always returns ≤ 1 KB unless `-v` is passed.
