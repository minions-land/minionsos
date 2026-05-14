---
slug: eacn3-error-recovery
summary: Open when an eacn3_* tool returns a non-400 error (timeout, 503, plugin crash) — decide retry / reconnect / escalate without losing in-flight work.
layer: logical
tools: eacn3_health, eacn3_cluster_status, eacn3_server_info, eacn3_get_task
version: 1
status: active
supersedes:
references: eacn3-bootstrap, eacn3-state-machines, eacn3-network-overview
provenance: human
---

# Skill — EACN3 Error Recovery

Decide what to do when an `eacn3_*` tool fails for reasons other than a 4xx state-machine violation. Covers the network / transport / plugin failure surface, not the protocol surface — for `400 Cannot collect results in status X` and similar, see `eacn3-state-machines`.

## When to invoke

- An `eacn3_*` tool call raised a transport error: connection refused, read timeout, TLS error, DNS failure.
- Server returned 5xx (typically `502 Forward failed`, `503 Network not initialized`).
- Plugin process died or stopped responding mid-tool-call.
- Heartbeat silently stopped (`eacn3_server_info` shows `remote_status: "unknown"`).

Do **not** invoke for 4xx errors — those are state-machine issues; use `eacn3-state-machines` instead.

## Structure

Three classes of failure, each with a distinct recovery action:

```
Transport (timeout, connection refused, DNS)
  → retry once with the same args; if still failing, treat as Network class.

Network (502 / 503 / cluster forwarding error)
  → eacn3_health on the configured endpoint.
  → If unhealthy: eacn3_cluster_status, find a healthy seed, eacn3_connect to it.
  → If healthy but still 5xx: escalate to Gru (transient cluster issue).

Plugin (crash, no heartbeat, server_info shows unknown)
  → MinionsOS: rely on the host's relaunch.
  → Standalone: eacn3_disconnect (best-effort), eacn3_connect, eacn3_claim_agent.
```

Recovery is bounded: at most one retry per failure class per tool call. Repeated failures escalate to Gru (cross-project relay, system repair, deadline risk) rather than looping locally.

State preservation: any in-flight task you initiated or executed survives plugin / session restart on the network side. Do not assume it is lost just because your session lost contact.

## Procedure

1. **Classify the error.** Read the exception message and tool name. Transport (timeout / refused / DNS), Network (502 / 503), or Plugin (no response / heartbeat dead) per the Structure table.
2. **Transport: retry once with the same arguments.** If the second call also fails, reclassify as Network and continue.
3. **Network: probe.** Call `eacn3_health(endpoint)` on the configured endpoint. If healthy, the 5xx was transient — wait briefly (30 s) and retry the original call. If unhealthy, call `eacn3_cluster_status` to find an online seed; reconnect to that seed via `eacn3_connect(network_endpoint=<seed>)`.
4. **Plugin (MinionsOS).** Do not try to restart yourself. Send a Gru relay message naming the failed tool and the error; Gru / the lifecycle will relaunch the host. Exit; the wakeup scheduler will rewake you when the queue is healthy again.
5. **Plugin (standalone).** Call `eacn3_disconnect()` (best-effort, ignore errors), then `eacn3_connect()`. If `available_agents` lists your previous identity, resume with `eacn3_claim_agent(<id>)`; otherwise re-register.
6. **After recovery, reconcile state.** For any task you had in flight, call `eacn3_get_task(task_id)` to read the network-authoritative state. Tasks the network already moved past your last-seen status are fine — pick up from the new status, do not redo work.
7. **Escalate to Gru** if any of: (a) two recovery attempts in the same failure class fail, (b) the failure blocks a deadline you committed to, (c) the failure pattern repeats across roles in the same project.

## Pitfalls

- Looping retries without classification — three retries on a `503 Network not initialized` are no better than one; the failure is structural until the network comes back.
- Assuming an in-flight task is lost because your session lost contact. The task lives on the network. After reconnect, `eacn3_get_task(task_id)` is authoritative — your local memory is not.
- Calling `eacn3_unregister_agent` to "clear state" after a transport error. This is destructive and will time out any task assignments you were holding. Recovery never includes unregistering.
- Treating a 502 from `forward_*` (cluster forwarding) the same as a 502 from a local tool. The forwarding case suggests a peer node is down — `eacn3_cluster_status` tells you which one, and the retry should target a different seed.
- (MinionsOS) Trying to call `eacn3_connect` from inside a Role wake when the host already manages the session. The host is the only thing that should restart the plugin.
