---
id: mos_exp_run
kind: tool
domain: experiments
auth: [expert]
source: minions/tools/mcp/experiment_tools.py:33
since: stable
keywords: [exp, run, gpu, training, ssh, local, command]
related: [mos_exp_status, mos_exp_wait, mos_exp_kill, mos_query_gpus]
status: stable
---

# mos_exp_run

**One line:** Run a one-off experiment with a long timeout.

## Signature
```py
mos_exp_run(
  command: str,
  cwd: str | None,
  execution: "local" | "ssh" | "auto",
  ssh_target: str | None,
  gpu_ids: list[int] | None,
  timeout_s: int | None,    # default ~7200
  log_path: str | None,     # absolute path; never the literal "{project_workspace}"
  env: dict[str,str] | None,
) -> { exp_id, started_at, log_path }
```

## Discipline
- `log_path` MUST be absolute under the calling Expert's branch. See pitfall-queue-deadlaunch-fp.
- `gpu_ids=[1]` is your safe 5-second probe default.
- `timeout_s ≥ 3600` for 30k-step grokking runs.
- For project venv (pandas, torch): `command="cd /proj && source .venv/bin/activate && python ..."`.

## Project_37596 lessons
- `mos_query_gpus(execution="auto")` rejected — pass `execution="local"`.
- Never run from inside `branches/<role>/...` if you'd `uv sync` — creates
  nested `.venv` and breaks MCP.

## See also
- domain-experiments
- pitfall-queue-deadlaunch-fp
- pitfall-project-venv
