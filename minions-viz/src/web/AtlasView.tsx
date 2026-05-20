import { useEffect, useState, useMemo } from "react";
import { useStore } from "./store";

interface AtlasNode {
  id: string;
  name: string;
  type: string;
  properties?: Record<string, any>;
}

interface AtlasEdge {
  source: string;
  target: string;
  relation: string;
  properties?: Record<string, any>;
}

interface AtlasGraph {
  nodes: AtlasNode[];
  edges: AtlasEdge[];
}

export function AtlasView() {
  const store = useStore();
  const gruId = store.selectedGruId;
  const port = store.selectedPort;
  const [graph, setGraph] = useState<AtlasGraph>({ nodes: [], edges: [] });
  const [selectedNode, setSelectedNode] = useState<AtlasNode | null>(null);
  const [filterType, setFilterType] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [layout, setLayout] = useState<"force" | "hierarchical" | "radial">("force");

  useEffect(() => {
    if (!gruId || port == null) return;
    setLoading(true);
    fetch(`/api/mos/project/${port}/atlas?gru=${gruId}`)
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
      <div className="atlas-view empty">
        <div className="empty-state">
          <div className="icon">🧠</div>
          <div className="message">Select a project to view atlas</div>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="atlas-view loading">
        <div className="spinner">Loading atlas...</div>
      </div>
    );
  }

  return (
    <div className="atlas-view">
      <div className="atlas-header">
        <div className="atlas-controls">
          <input
            type="text"
            className="atlas-search"
            placeholder="Search nodes..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          <select
            className="atlas-filter"
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
            className="atlas-layout"
            value={layout}
            onChange={(e) => setLayout(e.target.value as any)}
          >
            <option value="force">Force-Directed</option>
            <option value="hierarchical">Hierarchical</option>
            <option value="radial">Radial</option>
          </select>
        </div>
        <div className="atlas-stats">
          <span>{filteredGraph.nodes.length} nodes</span>
          <span>{filteredGraph.edges.length} edges</span>
          <span>{relationTypes.length} relation types</span>
        </div>
      </div>

      <div className="atlas-main">
        <div className="atlas-canvas">
          {filteredGraph.nodes.length === 0 ? (
            <div className="empty-state">
              <div className="icon">📭</div>
              <div className="message">
                {searchQuery || filterType !== "all"
                  ? "No matching nodes found"
                  : "No atlas data yet"}
              </div>
            </div>
          ) : (
            <AtlasGraphCanvas
              graph={filteredGraph}
              layout={layout}
              onNodeClick={setSelectedNode}
              selectedNode={selectedNode}
            />
          )}
        </div>

        {selectedNode && (
          <div className="atlas-detail-panel">
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

      <div className="atlas-legend">
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

function AtlasGraphCanvas({
  graph,
  layout,
  onNodeClick,
  selectedNode,
}: {
  graph: AtlasGraph;
  layout: string;
  onNodeClick: (node: AtlasNode) => void;
  selectedNode: AtlasNode | null;
}) {
  useEffect(() => {
    // TODO: D3 force/hierarchical/radial layouts; mirror ScratchpadView
    // Similar to ScratchpadView but for the corpus atlas
    // Support different layouts: force-directed, hierarchical, radial
  }, [graph, layout]);

  return (
    <div className="graph-canvas">
      <svg width="100%" height="100%">
        <text x="50%" y="50%" textAnchor="middle" fill="#666">
          Atlas visualization coming soon...
        </text>
      </svg>
    </div>
  );
}
