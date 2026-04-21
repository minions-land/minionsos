import json
from datetime import datetime
from pathlib import Path
import sys


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    if payload.get("hook_event_name") != "SubagentStop":
        return 0

    agent_type = payload.get("agent_type", "")
    if not agent_type.startswith("paper-"):
        return 0

    log_dir = Path(".claude") / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "subagent-events.md"

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    stop_reason = payload.get("stop_reason", "")
    summary = (
        payload.get("last_assistant_message")
        or payload.get("message")
        or "(no summary)"
    ).strip()

    entry = [
        f"## {timestamp} | {agent_type}",
        "",
        f"- stop_reason: `{stop_reason or 'unknown'}`",
        "",
        "```text",
        summary,
        "```",
        "",
    ]

    with log_path.open("a", encoding="utf-8") as f:
        f.write("\n".join(entry))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
