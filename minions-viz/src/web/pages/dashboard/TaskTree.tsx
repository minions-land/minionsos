import { TreeStructure } from "@phosphor-icons/react";
import { shortId, truncate, statusColor } from "../../utils/format";
import EmptyState from "../../components/EmptyState";
import type { Task } from "@shared/types";

interface Props {
  tasks: Task[];
  onSelect: (id: string) => void;
}

function taskDescription(t: Task): string {
  if (typeof t.content?.description === "string") return t.content.description;
  if (typeof t.content?.content === "string") return t.content.content;
  return "";
}

export default function TaskTree({ tasks, onSelect }: Props) {
  const taskMap = new Map(tasks.map((t) => [t.id, t]));
  const roots = tasks.filter((t) => !t.parent_id);

  if (roots.length === 0) {
    return <EmptyState icon={TreeStructure} message="No task hierarchy found" />;
  }

  function renderNode(task: Task, depth: number) {
    const children = task.child_ids
      .map((cid) => taskMap.get(cid))
      .filter(Boolean) as Task[];

    return (
      <div key={task.id} style={{ marginLeft: depth * 20 }}>
        <button
          onClick={() => onSelect(task.id)}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "5px 8px",
            width: "100%",
            textAlign: "left",
            cursor: "pointer",
            background: "transparent",
            border: "none",
            borderRadius: 4,
            transition: "background 0.15s",
          }}
          onMouseEnter={(e) => (e.currentTarget.style.background = "var(--surface)")}
          onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
        >
          <span
            className={statusColor(task.status)}
            style={{ width: 8, height: 8, borderRadius: "50%", flexShrink: 0, display: "inline-block" }}
          />
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)" }}>
            {shortId(task.id)}
          </span>
          <span style={{ fontSize: 11, color: "var(--text-2)" }}>
            {truncate(taskDescription(task), 60) || "(no description)"}
          </span>
        </button>
        {children.map((child) => renderNode(child, depth + 1))}
      </div>
    );
  }

  return (
    <div
      className="scroll-region"
      style={{
        maxHeight: 360,
        background: "var(--panel-bg)",
        borderRadius: 8,
        border: "1px solid var(--line)",
        padding: 8,
      }}
    >
      {roots.map((r) => renderNode(r, 0))}
    </div>
  );
}
