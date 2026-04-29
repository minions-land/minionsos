import type { NetworkSnapshot } from "@shared/types";
import MetricBar from "./MetricBar";
import AgentsPanel from "./AgentsPanel";
import TasksPanel from "./TasksPanel";
import MessagesPanel from "./MessagesPanel";

interface Props {
  store: NetworkSnapshot;
  onSelectAgent: (id: string) => void;
  onSelectTask: (id: string) => void;
}

export default function DashboardPage({ store, onSelectAgent, onSelectTask }: Props) {
  return (
    <div className="page-container">
      <div className="max-w-[1600px] mx-auto space-y-5">
        <MetricBar agents={store.agents} tasks={store.tasks} messageCount={store.messages.length} connected={store.connected} />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <div className="panel-card"><AgentsPanel agents={store.agents} onSelect={onSelectAgent} /></div>
          <div className="panel-card"><TasksPanel tasks={store.tasks} agents={store.agents} onSelect={onSelectTask} /></div>
        </div>
        <div className="panel-card"><MessagesPanel messages={store.messages} logs={store.logs} agents={store.agents} /></div>
      </div>
    </div>
  );
}
