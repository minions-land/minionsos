import { useEffect, useState, useMemo } from "react";
import { useStore } from "./store";

interface KGNode {
  id: string;
  name: string;
  type: string;
  properties?: Record<string, any>;
}

interface KGEdge {
  source: string;
  target: string;
  relation: string;
  properties?: Record<string, any>;
}

interface KnowledgeGraph {
  nodes: KGNode[];
  edges: KGEdge[];
}

export function KnowledgeGraphView() {
  const store = useStore();
  const gruId = store.selectedGruId;
  const port = store.selectedPort;
  const [graph, setGraph] = useState<KnowledgeGraph>({ nodes: [], edges: [] });
  const [selectedNode, setSelectedNode] = useState<KGNode | null>(null);
  const [filterType, setFilterType] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [layout, setLayout] = useState<"force" | "hierarchical" | "radial">("force");

  useEffect(() => {
    if (!gruId || port == null) return;
    setLoading(true);
    fetch(`/api/mos/project/${port}/knowledge-graph?gru=${gruId}`)
      .then((r) => r.json())
      .then((data) => {
        setGraph({
          nodes: data.entities || [],
          edges: data.relations || [],
        });
        setLoading(false);
      })
      .catch(() => {
        setGraph({ nodes: [], edges: [] });
        setLoading(false);
      });
  }, [gruId, port]);

  const nodeTypes = useMemo(() => {
    const types = new Set(graph.nodes.map((n) => n.type));
    return ["all", ...Array.from(types).sort()];
  }, [graph]);

  const filteredGraph = useMemo(() => {
    let nodes = graph.nodes;
    let edges = graph.edges;

    // Filter by type
    if (filterType !== "all") {
      nodes = nodes.filter((n) => n.type === filterType);
      const nodeIds = new Set(nodes.map((n) => n.id));
      edges = edges.filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target));
    }

    // Filter by search query
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      nodes = nodes.filter(
        (n) =>
          n.name.toLowerCase().includes(q) ||
          n.type.toLowerCase().includes(q) ||
          (n.properties && JSON.stringify(n.properties).toLowerCase().includes(q))
      );
      const nodeIds = new Set(nodes.map((n) => n.id));
      edges = edges.filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target));
    }

    return { nodes, edges };
  }, [graph, filterType, searchQuery]);

  const relationTypes = useMemo(() => {
    const types = new Set(filteredGraph.edges.map((e) => e.relation));
    return Array.from(types).sort();
  }, [filteredGraph]);

  if (!gruId || port == null) {
    return (
      <div className="knowledge-graph-view empty">
        <div className="empty-state">
          <div className="icon">🧠</div>
          <div className="message">Select a project to view knowledge graph</div>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="knowledge-graph-view loading">
        <div className="spinner">Loading knowledge graph...</div>
      </div>
    );
  }

  return (
    <div className="knowledge-graph-view">
      <div className="kg-header">
        <div className="kg-controls">
          <input
            type="text"
            className="kg-search"
            placeholder="Search nodes..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          <select
            className="kg-filter"
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
          >
            {nodeTypes.map((type) => (
              <option key={type} value={type}>
                {type === "all" ? "All Types" : type}
              </option>
            ))}
          </select>
          <select
            className="kg-layout"
            value={layout}
            onChange={(e) => setLayout(e.target.value as any)}
          >
            <option value="force">Force-Directed</option>
            <option value="hierarchical">Hierarchical</option>
            <option value="radial">Radial</option>
          </select>
        </div>
        <div className="kg-stats">
          <span>{filteredGraph.nodes.length} nodes</span>
          <span>{filteredGraph.edges.length} edges</span>
          <span>{relationTypes.length} relation types</span>
        </div>
      </div>

      <div className="kg-main">
        <div className="kg-canvas">
          {filteredGraph.nodes.length === 0 ? (
            <div className="empty-state">
              <div className="icon">📭</div>
              <div className="message">
                {searchQuery || filterType !== "all"
                  ? "No matching nodes found"
                  : "No knowledge graph data yet"}
              </div>
            </div>
          ) : (
            <KGGraphCanvas
              graph={filteredGraph}
              layout={layout}
              onNodeClick={setSelectedNode}
              selectedNode={selectedNode}
            />
          )}
        </div>

        {selectedNode && (
          <div className="kg-detail-panel">
            <div className="panel-header">
              <h3>{selectedNode.name}</h3>
              <button className="close-btn" onClick={() => setSelectedNode(null)}>
                ✕
              </button>
            </div>
            <div className="panel-content">
              <div className="node-type">
                <strong>Type:</strong> {selectedNode.type}
              </div>
              {selectedNode.properties && Object.keys(selectedNode.properties).length > 0 && (
                <div className="node-properties">
                  <strong>Properties:</strong>
                  <ul>
                    {Object.entries(selectedNode.properties).map(([key, value]) => (
                      <li key={key}>
                        <span className="prop-key">{key}:</span>
                        <span className="prop-value">{JSON.stringify(value)}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <div className="node-connections">
                <strong>Connections:</strong>
                <div className="connections-list">
                  <div className="outgoing">
                    <h4>Outgoing ({filteredGraph.edges.filter((e) => e.source === selectedNode.id).length})</h4>
                    <ul>
                      {filteredGraph.edges
                        .filter((e) => e.source === selectedNode.id)
                        .map((edge, i) => {
                          const target = filteredGraph.nodes.find((n) => n.id === edge.target);
                          return (
                            <li key={i}>
                              <span className="relation">{edge.relation}</span>
                              <span className="arrow">→</span>
                              <a
                                href="#"
                                onClick={(e) => {
                                  e.preventDefault();
                                  if (target) setSelectedNode(target);
                                }}
                              >
                                {target?.name || edge.target}
                              </a>
                            </li>
                          );
                        })}
                    </ul>
                  </div>
                  <div className="incoming">
                    <h4>Incoming ({filteredGraph.edges.filter((e) => e.target === selectedNode.id).length})</h4>
                    <ul>
                      {filteredGraph.edges
                        .filter((e) => e.target === selectedNode.id)
                        .map((edge, i) => {
                          const source = filteredGraph.nodes.find((n) => n.id === edge.source);
                          return (
                            <li key={i}>
                              <a
                                href="#"
                                onClick={(e) => {
                                  e.preventDefault();
                                  if (source) setSelectedNode(source);
                                }}
                              >
                                {source?.name || edge.source}
                              </a>
                              <span className="arrow">→</span>
                              <span className="relation">{edge.relation}</span>
                            </li>
                          );
                        })}
                    </ul>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="kg-legend">
        <h4>Node Types</h4>
        <div className="legend-items">
          {nodeTypes
            .filter((t) => t !== "all")
            .map((type) => (
              <div key={type} className="legend-item">
                <div className={`legend-color type-${type}`} />
                <span>{type}</span>
                <span className="count">
                  ({graph.nodes.filter((n) => n.type === type).length})
                </span>
              </div>
            ))}
        </div>
      </div>
    </div>
  );
}

function KGGraphCanvas({
  graph,
  layout,
  onNodeClick,
  selectedNode,
}: {
  graph: KnowledgeGraph;
  layout: string;
  onNodeClick: (node: KGNode) => void;
  selectedNode: KGNode | null;
}) {
  useEffect(() => {
    // TODO: Implement D3.js graph visualization
    // Similar to DagView but for knowledge graph
    // Support different layouts: force-directed, hierarchical, radial
  }, [graph, layout]);

  return (
    <div className="graph-canvas">
      <svg width="100%" height="100%">
        <text x="50%" y="50%" textAnchor="middle" fill="#666">
          Knowledge graph visualization coming soon...
        </text>
      </svg>
    </div>
  );
}
