import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import type { DraftNode, DraftEdge, DraftData } from "@shared/types";
import { useStore } from "./store";

// ── Constants ─────────────────────────────────────────────────────

const NODE_TYPE_COLORS: Record<string, string> = {
  hypothesis: "#f59e0b",
  question: "#60a5fa",
  assumption: "#a78bfa",
  experiment: "#fb923c",
  result: "#34d399",
  citation: "#94a3b8",
  decision: "#c084fc",
  dead_end: "#f87171",
  insight: "#22d3ee",
  method: "#4ade80",
};

const STATUS_OPACITY: Record<string, number> = {
  verified: 1.0,
  tentative: 0.85,
  unverified: 0.7,
  refuted: 0.4,
  blocked: 0.5,
  out_of_scope: 0.35,
};

const RELATION_STYLES: Record<string, { dash: string; color: string; width: number }> = {
  refines: { dash: "", color: "rgba(160,180,220,0.5)", width: 2 },
  tests: { dash: "6 3", color: "rgba(251,146,60,0.6)", width: 2.5 },
  supports: { dash: "", color: "rgba(52,211,153,0.6)", width: 2.5 },
  contradicts: { dash: "4 4", color: "rgba(248,113,113,0.7)", width: 2.5 },
  depends_on: { dash: "", color: "rgba(96,165,250,0.5)", width: 2 },
  derived_from: { dash: "8 4", color: "rgba(192,132,252,0.5)", width: 2 },
  supersedes: { dash: "", color: "rgba(251,191,36,0.6)", width: 2 },
  cites: { dash: "2 4", color: "rgba(148,163,184,0.4)", width: 1.5 },
  blocks: { dash: "4 2", color: "rgba(248,113,113,0.6)", width: 2.5 },
};

const NODE_RADIUS = 28;
const LABEL_OFFSET = 38;

// ── Force simulation ──────────────────────────────────────────────

interface SimNode {
  id: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
  fx: number | null;
  fy: number | null;
  data: DraftNode;
  timeRank: number;
  layer: number; // Hierarchical layer for better visual organization
}

interface SimEdge {
  source: string;
  target: string;
  data: DraftEdge;
}

// Compute hierarchical layers using topological sort
function computeHierarchicalLayers(nodes: DraftNode[], edges: DraftEdge[]): Map<string, number> {
  const layers = new Map<string, number>();
  const inDegree = new Map<string, number>();
  const outEdges = new Map<string, string[]>();

  // Initialize
  nodes.forEach(n => {
    inDegree.set(n.id, 0);
    outEdges.set(n.id, []);
  });

  // Build graph
  edges.forEach(e => {
    inDegree.set(e.to_id, (inDegree.get(e.to_id) || 0) + 1);
    outEdges.get(e.from_id)?.push(e.to_id);
  });

  // Topological sort with layer assignment
  const queue: string[] = [];
  nodes.forEach(n => {
    if (inDegree.get(n.id) === 0) {
      queue.push(n.id);
      layers.set(n.id, 0);
    }
  });

  while (queue.length > 0) {
    const current = queue.shift()!;
    const currentLayer = layers.get(current) || 0;

    outEdges.get(current)?.forEach(next => {
      const deg = inDegree.get(next)! - 1;
      inDegree.set(next, deg);

      const nextLayer = Math.max(layers.get(next) || 0, currentLayer + 1);
      layers.set(next, nextLayer);

      if (deg === 0) {
        queue.push(next);
      }
    });
  }

  // Handle cycles - assign remaining nodes to layer 0
  nodes.forEach(n => {
    if (!layers.has(n.id)) {
      layers.set(n.id, 0);
    }
  });

  return layers;
}

function runForceStep(nodes: SimNode[], edges: SimEdge[], width: number, height: number) {
  const alpha = 0.25;
  const repulsion = 12000;
  const attraction = 0.01;
  const damping = 0.82;
  const centerForce = 0.015;
  const layerGravity = 0.08; // Strong layer-based vertical positioning
  const timeGravity = 0.015;

  const nodeMap = new Map(nodes.map((n) => [n.id, n]));
  const maxLayer = Math.max(...nodes.map(n => n.layer || 0), 0);

  // Repulsion with same-layer boost
  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      const a = nodes[i], b = nodes[j];
      let dx = b.x - a.x, dy = b.y - a.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;

      // Stronger repulsion for same-layer nodes
      const sameLayer = (a.layer === b.layer) ? 1.5 : 1.0;
      const force = (repulsion * sameLayer) / (dist * dist);

      dx = (dx / dist) * force;
      dy = (dy / dist) * force;
      a.vx -= dx * alpha;
      a.vy -= dy * alpha;
      b.vx += dx * alpha;
      b.vy += dy * alpha;
    }
  }

  // Attraction along edges
  for (const edge of edges) {
    const a = nodeMap.get(edge.source);
    const b = nodeMap.get(edge.target);
    if (!a || !b) continue;
    const dx = b.x - a.x, dy = b.y - a.y;
    const dist = Math.sqrt(dx * dx + dy * dy) || 1;
    const strength = edge.data.strength * attraction;
    const fx = dx * strength, fy = dy * strength;
    a.vx += fx * alpha;
    a.vy += fy * alpha;
    b.vx -= fx * alpha;
    b.vy -= fy * alpha;
  }

  // Center gravity
  const cx = width / 2, cy = height / 2;
  for (const node of nodes) {
    node.vx += (cx - node.x) * centerForce * alpha;
    node.vy += (cy - node.y) * centerForce * alpha;
  }

  // Layer-based vertical positioning (main visual improvement)
  for (const node of nodes) {
    const layerProgress = maxLayer > 0 ? (node.layer || 0) / maxLayer : 0.5;
    const targetY = height * 0.15 + layerProgress * height * 0.7;
    node.vy += (targetY - node.y) * layerGravity * alpha;
  }

  // Time-based horizontal nudge
  for (const node of nodes) {
    const targetX = cx + (node.timeRank - 0.5) * width * 0.3;
    node.vx += (targetX - node.x) * timeGravity * alpha;
  }

  // Apply velocities
  for (const node of nodes) {
    if (node.fx != null) { node.x = node.fx; node.vx = 0; }
    else { node.vx *= damping; node.x += node.vx; }
    if (node.fy != null) { node.y = node.fy; node.vy = 0; }
    else { node.vy *= damping; node.y += node.vy; }
    // Bounds
    node.x = Math.max(NODE_RADIUS + 10, Math.min(width - NODE_RADIUS - 10, node.x));
    node.y = Math.max(NODE_RADIUS + 10, Math.min(height - NODE_RADIUS - 10, node.y));
  }
}

// ── Component ─────────────────────────────────────────────────────

type SortMode = "time" | "type" | "status";
type FilterState = {
  types: Set<string>;
  statuses: Set<string>;
  roles: Set<string>;
  search: string;
};

export default function DraftView() {
  const store = useStore();
  const [draft, setDraft] = useState<DraftData | null>(null);
  const [simNodes, setSimNodes] = useState<SimNode[]>([]);
  const [simEdges, setSimEdges] = useState<SimEdge[]>([]);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [sortMode, setSortMode] = useState<SortMode>("time");
  const [filter, setFilter] = useState<FilterState>({
    types: new Set(), statuses: new Set(), roles: new Set(), search: "",
  });
  const [dragNode, setDragNode] = useState<string | null>(null);
  const [transform, setTransform] = useState({ x: 0, y: 0, scale: 1 });
  const [isPanning, setIsPanning] = useState(false);
  const [panStart, setPanStart] = useState({ x: 0, y: 0, tx: 0, ty: 0 });
  const dragRef = useRef<{ id: string; startX: number; startY: number; moved: boolean } | null>(null);

  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const animRef = useRef<number>(0);
  const nodesRef = useRef<SimNode[]>([]);
  const edgesRef = useRef<SimEdge[]>([]);
  const sizeRef = useRef({ width: 900, height: 600 });

  const gruId = store.selectedGruId;
  const port = store.selectedPort;

  // Fetch draft data
  useEffect(() => {
    if (!gruId || port == null) return;
    let cancelled = false;
    const fetchDraft = () => {
      fetch(`/api/mos/project/${port}/draft?gru=${gruId}`)
        .then((r) => r.ok ? r.json() : null)
        .then((data) => {
          if (cancelled || !data) return;
          // Defensive: ensure required arrays exist before handing to the
          // simulation. The server-side endpoint already guards this, but
          // an out-of-date or proxied server could still return a partial
          // shape — in which case we'd rather show "No draft" than crash
          // the React tree (see GitHub Issue / user-Q2: tab lockup).
          const safe: DraftData = {
            project_port: typeof data.project_port === "number" ? data.project_port : (port ?? 0),
            root_question: typeof data.root_question === "string" ? data.root_question : "",
            nodes: Array.isArray(data.nodes) ? data.nodes : [],
            edges: Array.isArray(data.edges) ? data.edges : [],
          };
          setDraft(safe);
        })
        .catch(() => {});
    };
    fetchDraft();
    const interval = setInterval(fetchDraft, 8000);
    return () => { cancelled = true; clearInterval(interval); };
  }, [gruId, port]);

  // Initialize simulation nodes when draft changes
  useEffect(() => {
    if (!draft || draft.nodes.length === 0) {
      nodesRef.current = [];
      edgesRef.current = [];
      setSimNodes([]);
      setSimEdges([]);
      return;
    }

    const { width, height } = sizeRef.current;

    // Compute hierarchical layers
    const layerMap = computeHierarchicalLayers(draft.nodes, draft.edges);

    // Compute rank based on sort mode
    let ranked: DraftNode[];
    if (sortMode === "type") {
      const typeOrder = Object.keys(NODE_TYPE_COLORS);
      ranked = [...draft.nodes].sort((a, b) => typeOrder.indexOf(a.type) - typeOrder.indexOf(b.type));
    } else if (sortMode === "status") {
      const statusOrder = ["verified", "tentative", "unverified", "blocked", "refuted", "out_of_scope"];
      ranked = [...draft.nodes].sort((a, b) => statusOrder.indexOf(a.support_status) - statusOrder.indexOf(b.support_status));
    } else {
      ranked = [...draft.nodes].sort((a, b) => (a.created_at || "").localeCompare(b.created_at || ""));
    }
    const rankMap = new Map(ranked.map((n, i) => [n.id, i / Math.max(1, ranked.length - 1)]));

    const existingMap = new Map(nodesRef.current.map((n) => [n.id, n]));
    const nodes: SimNode[] = draft.nodes.map((n) => {
      const existing = existingMap.get(n.id);
      const layer = layerMap.get(n.id) || 0;
      if (existing) {
        existing.data = n;
        existing.timeRank = rankMap.get(n.id) ?? 0.5;
        existing.layer = layer;
        return existing;
      }
      return {
        id: n.id,
        x: width * 0.3 + Math.random() * width * 0.4,
        y: height * 0.3 + Math.random() * height * 0.4,
        vx: 0, vy: 0, fx: null, fy: null,
        data: n,
        timeRank: rankMap.get(n.id) ?? 0.5,
        layer,
      };
    });

    const edges: SimEdge[] = draft.edges.map((e) => ({
      source: e.from_id, target: e.to_id, data: e,
    }));

    nodesRef.current = nodes;
    edgesRef.current = edges;
    setSimNodes([...nodes]);
    setSimEdges(edges);
  }, [draft, sortMode]);

  // Animation loop
  useEffect(() => {
    let running = true;
    let frame = 0;
    const tick = () => {
      if (!running) return;
      const nodes = nodesRef.current;
      const edges = edgesRef.current;
      if (nodes.length > 0) {
        const { width, height } = sizeRef.current;
        runForceStep(nodes, edges, width, height);
        frame++;
        if (frame % 2 === 0) setSimNodes([...nodes]);
      }
      animRef.current = requestAnimationFrame(tick);
    };
    animRef.current = requestAnimationFrame(tick);
    return () => { running = false; cancelAnimationFrame(animRef.current); };
  }, []);

  // Resize observer
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const obs = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      sizeRef.current = { width, height };
    });
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  // Filter nodes
  const visibleNodes = useMemo(() => {
    return simNodes.filter((n) => {
      if (filter.types.size > 0 && !filter.types.has(n.data.type)) return false;
      if (filter.statuses.size > 0 && !filter.statuses.has(n.data.support_status)) return false;
      if (filter.roles.size > 0 && !filter.roles.has(n.data.author_role)) return false;
      if (filter.search) {
        const s = filter.search.toLowerCase();
        if (!n.data.text.toLowerCase().includes(s) && !n.data.id.toLowerCase().includes(s)) return false;
      }
      return true;
    });
  }, [simNodes, filter]);

  const visibleIds = useMemo(() => new Set(visibleNodes.map((n) => n.id)), [visibleNodes]);

  const visibleEdges = useMemo(() => {
    return simEdges.filter((e) => visibleIds.has(e.source) && visibleIds.has(e.target));
  }, [simEdges, visibleIds]);

  // Connected nodes for highlight
  const connectedToSelected = useMemo(() => {
    if (!selectedNode) return new Set<string>();
    const ids = new Set<string>();
    for (const e of simEdges) {
      if (e.source === selectedNode) ids.add(e.target);
      if (e.target === selectedNode) ids.add(e.source);
    }
    return ids;
  }, [selectedNode, simEdges]);

  // All unique types/statuses/roles for filter UI
  const allTypes = useMemo(() => [...new Set(draft?.nodes.map((n) => n.type) ?? [])].sort(), [draft]);
  const allStatuses = useMemo(() => [...new Set(draft?.nodes.map((n) => n.support_status) ?? [])].sort(), [draft]);
  const allRoles = useMemo(() => [...new Set(draft?.nodes.map((n) => n.author_role).filter(Boolean) ?? [])].sort(), [draft]);

  const selectedNodeData = useMemo(
    () => simNodes.find((n) => n.id === selectedNode)?.data ?? null,
    [simNodes, selectedNode]
  );

  // Drag handlers — pin node only AFTER mouse moves past a threshold,
  // so a clean click never sticks the node to the cursor. mousemove and
  // mouseup are wired to `window` (not the SVG) so that releasing the
  // button outside the canvas — or in any "missed mouseup" case — still
  // releases the node.
  const DRAG_THRESHOLD = 4;

  const handleNodeMouseDown = useCallback((e: React.MouseEvent, nodeId: string) => {
    e.stopPropagation();
    e.preventDefault();
    setDragNode(nodeId);
    dragRef.current = { id: nodeId, startX: e.clientX, startY: e.clientY, moved: false };
  }, []);

  const handleBgMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.button === 0 && !dragNode) {
      setIsPanning(true);
      setPanStart({ x: e.clientX, y: e.clientY, tx: transform.x, ty: transform.y });
    }
  }, [dragNode, transform]);

  // Window-level mousemove / mouseup. Lives in an effect so listeners
  // are added exactly once per (dragNode, isPanning, panStart) state.
  useEffect(() => {
    function release() {
      if (dragRef.current) {
        const node = nodesRef.current.find((n) => n.id === dragRef.current!.id);
        if (node) { node.fx = null; node.fy = null; }
        dragRef.current = null;
      }
      setDragNode(null);
      setIsPanning(false);
    }

    function onMove(e: MouseEvent) {
      // Safety release: any active gesture but no button is held → drop pin.
      // Catches "missed mouseup" cases (release outside window, focus
      // change, OS-level interruption, etc.).
      if (e.buttons === 0 && (dragRef.current || isPanning)) {
        release();
        return;
      }
      if (dragRef.current && dragNode) {
        const dx = e.clientX - dragRef.current.startX;
        const dy = e.clientY - dragRef.current.startY;
        if (!dragRef.current.moved && Math.hypot(dx, dy) < DRAG_THRESHOLD) return;
        dragRef.current.moved = true;
        const svg = svgRef.current;
        if (!svg) return;
        const rect = svg.getBoundingClientRect();
        const x = (e.clientX - rect.left - transform.x) / transform.scale;
        const y = (e.clientY - rect.top - transform.y) / transform.scale;
        const node = nodesRef.current.find((n) => n.id === dragNode);
        if (node) { node.fx = x; node.fy = y; node.x = x; node.y = y; }
      } else if (isPanning) {
        const dx = e.clientX - panStart.x;
        const dy = e.clientY - panStart.y;
        setTransform((t) => ({ ...t, x: panStart.tx + dx, y: panStart.ty + dy }));
      }
    }

    function onUp(e: MouseEvent) {
      if (dragRef.current && dragNode) {
        const node = nodesRef.current.find((n) => n.id === dragNode);
        if (dragRef.current.moved) {
          if (node) { node.fx = null; node.fy = null; }
        } else {
          setSelectedNode((cur) => (cur === dragNode ? null : dragNode));
        }
        dragRef.current = null;
        setDragNode(null);
      } else if (isPanning) {
        const movedX = Math.abs(e.clientX - panStart.x);
        const movedY = Math.abs(e.clientY - panStart.y);
        if (movedX < DRAG_THRESHOLD && movedY < DRAG_THRESHOLD) {
          setSelectedNode(null);
        }
      }
      setIsPanning(false);
    }

    function onBlur() { release(); }

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    window.addEventListener("blur", onBlur);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      window.removeEventListener("blur", onBlur);
    };
  }, [dragNode, isPanning, panStart, transform.x, transform.y, transform.scale]);

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    setTransform((t) => {
      const newScale = Math.max(0.2, Math.min(4, t.scale * delta));
      const ratio = newScale / t.scale;
      return {
        scale: newScale,
        x: mx - (mx - t.x) * ratio,
        y: my - (my - t.y) * ratio,
      };
    });
  }, []);

  // Edge path with curve
  const edgePath = useCallback((source: SimNode, target: SimNode) => {
    const dx = target.x - source.x;
    const dy = target.y - source.y;
    const dist = Math.sqrt(dx * dx + dy * dy);
    if (dist < 1) return "";
    const curve = dist * 0.15;
    const mx = (source.x + target.x) / 2 - (dy / dist) * curve;
    const my = (source.y + target.y) / 2 + (dx / dist) * curve;
    return `M ${source.x} ${source.y} Q ${mx} ${my} ${target.x} ${target.y}`;
  }, []);

  const toggleFilter = useCallback((key: "types" | "statuses" | "roles", value: string) => {
    setFilter((f) => {
      const next = new Set(f[key]);
      if (next.has(value)) next.delete(value); else next.add(value);
      return { ...f, [key]: next };
    });
  }, []);

  const nodeMap = useMemo(() => new Map(simNodes.map((n) => [n.id, n])), [simNodes]);

  if (!draft || (draft.nodes.length === 0 && !draft.root_question)) {
    return (
      <div className="draft-wrap">
        <div className="empty">
          <span style={{ fontSize: 14 }}>No draft</span>
          <span>This project hasn't started building its draft yet</span>
        </div>
      </div>
    );
  }

  return (
    <div className="draft-wrap" ref={containerRef}>
      {/* Toolbar */}
      <div className="draft-toolbar">
        <input
          className="draft-search"
          placeholder="Search nodes..."
          value={filter.search}
          onChange={(e) => setFilter((f) => ({ ...f, search: e.target.value }))}
        />
        <div className="draft-filters">
          {allTypes.map((t) => (
            <button
              key={t}
              className={`draft-filter-chip ${filter.types.has(t) ? "active" : ""}`}
              style={{ "--chip-color": NODE_TYPE_COLORS[t] || "#7a8aa8" } as React.CSSProperties}
              onClick={() => toggleFilter("types", t)}
            >
              <span className="draft-chip-dot" />
              {t}
            </button>
          ))}
        </div>
        <div className="draft-sort">
          <span className="draft-sort-label">Layout</span>
          <div className="seg">
            <button className={sortMode === "time" ? "active" : ""} onClick={() => setSortMode("time")}>Time</button>
            <button className={sortMode === "type" ? "active" : ""} onClick={() => setSortMode("type")}>Type</button>
            <button className={sortMode === "status" ? "active" : ""} onClick={() => setSortMode("status")}>Status</button>
          </div>
        </div>
        <div className="draft-stats">
          <span className="draft-stat">{draft.nodes.length} nodes</span>
          <span className="draft-stat">{draft.edges.length} edges</span>
        </div>
      </div>

      {/* Root question banner */}
      {draft.root_question && (
        <div className="draft-root-question">
          <span className="draft-rq-label">Root Question</span>
          <span className="draft-rq-text">{draft.root_question}</span>
        </div>
      )}

      {/* SVG Canvas */}
      <svg
        ref={svgRef}
        className="draft-canvas"
        onMouseDown={handleBgMouseDown}
        onWheel={handleWheel}
      >
        <defs>
          <filter id="draft-glow">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <filter id="draft-glow-strong">
            <feGaussianBlur stdDeviation="6" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <marker id="draft-arrow" viewBox="0 0 10 10" refX="8" refY="5"
            markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="rgba(160,180,220,0.5)" />
          </marker>
        </defs>
        <g transform={`translate(${transform.x},${transform.y}) scale(${transform.scale})`}>
          {/* Edges */}
          {visibleEdges.map((edge, i) => {
            const source = nodeMap.get(edge.source);
            const target = nodeMap.get(edge.target);
            if (!source || !target) return null;
            const style = RELATION_STYLES[edge.data.relation] || RELATION_STYLES.refines;
            const isHighlighted = selectedNode && (edge.source === selectedNode || edge.target === selectedNode);
            const dimmed = selectedNode && !isHighlighted;
            return (
              <path
                key={`${edge.source}-${edge.target}-${i}`}
                d={edgePath(source, target)}
                fill="none"
                stroke={isHighlighted ? style.color.replace(/[\d.]+\)$/, "0.9)") : style.color}
                strokeWidth={isHighlighted ? 2.5 : 1.5}
                strokeDasharray={style.dash}
                opacity={dimmed ? 0.15 : 1}
                markerEnd="url(#draft-arrow)"
                className="draft-edge"
              />
            );
          })}

          {/* Nodes */}
          {visibleNodes.map((node) => {
            const color = NODE_TYPE_COLORS[node.data.type] || "#7a8aa8";
            const opacity = STATUS_OPACITY[node.data.support_status] ?? 0.7;
            const isSelected = node.id === selectedNode;
            const isHovered = node.id === hoveredNode;
            const isConnected = connectedToSelected.has(node.id);
            const dimmed = selectedNode && !isSelected && !isConnected;
            const radius = isSelected ? NODE_RADIUS + 4 : isHovered ? NODE_RADIUS + 2 : NODE_RADIUS;

            return (
              <g
                key={node.id}
                transform={`translate(${node.x},${node.y})`}
                opacity={dimmed ? 0.25 : opacity}
                className="draft-node-group"
                onMouseDown={(e) => handleNodeMouseDown(e, node.id)}
                onMouseEnter={() => setHoveredNode(node.id)}
                onMouseLeave={() => setHoveredNode(null)}
                style={{ cursor: "pointer" }}
              >
                {/* Outer glow ring */}
                {(isSelected || isHovered) && (
                  <circle r={radius + 6} fill="none" stroke={color}
                    strokeWidth={1.5} opacity={0.4} filter="url(#draft-glow)" />
                )}
                {/* Node circle */}
                <circle
                  r={radius}
                  fill={`${color}22`}
                  stroke={color}
                  strokeWidth={isSelected ? 2.5 : 1.5}
                  filter={isSelected ? "url(#draft-glow-strong)" : undefined}
                />
                {/* Type icon (first letter) */}
                <text
                  textAnchor="middle" dominantBaseline="central"
                  fill={color} fontSize={12} fontWeight={600}
                  fontFamily="var(--font-mono)"
                  style={{ pointerEvents: "none" }}
                >
                  {node.data.id}
                </text>
                {/* Label below */}
                <text
                  y={LABEL_OFFSET}
                  textAnchor="middle" dominantBaseline="hanging"
                  fill="var(--text-2)" fontSize={10}
                  fontFamily="var(--font-sans)"
                  style={{ pointerEvents: "none" }}
                >
                  {node.data.text.length > 30 ? node.data.text.slice(0, 28) + "..." : node.data.text}
                </text>
                {/* Status indicator */}
                {node.data.support_status === "verified" && (
                  <circle cx={radius - 4} cy={-radius + 4} r={4} fill="#34d399" />
                )}
                {node.data.support_status === "refuted" && (
                  <circle cx={radius - 4} cy={-radius + 4} r={4} fill="#f87171" />
                )}
                {node.data.support_status === "blocked" && (
                  <circle cx={radius - 4} cy={-radius + 4} r={4} fill="#fbbf24" />
                )}
              </g>
            );
          })}
        </g>
      </svg>

      {/* Detail panel */}
      {selectedNodeData && (
        <div className="draft-detail">
          <div className="draft-detail-header">
            <span className="draft-detail-id" style={{ color: NODE_TYPE_COLORS[selectedNodeData.type] || "#7a8aa8" }}>
              {selectedNodeData.id}
            </span>
            <span className={`badge ${selectedNodeData.support_status === "verified" ? "active" : selectedNodeData.support_status === "blocked" ? "sleeping" : ""}`}>
              {selectedNodeData.support_status}
            </span>
            <button className="draft-detail-close" onClick={() => setSelectedNode(null)}>×</button>
          </div>
          <div className="draft-detail-body">
            <div className="draft-detail-text">{selectedNodeData.text}</div>
            <dl className="draft-detail-meta">
              <dt>Type</dt><dd>{selectedNodeData.type}</dd>
              <dt>Author</dt><dd>{selectedNodeData.author_role || "—"}</dd>
              <dt>Created</dt><dd>{selectedNodeData.created_at ? new Date(selectedNodeData.created_at).toLocaleString() : "—"}</dd>
              {selectedNodeData.evidence_tag && (<><dt>Evidence</dt><dd>{selectedNodeData.evidence_tag}</dd></>)}
              {Object.keys(selectedNodeData.metadata || {}).length > 0 && (
                <><dt>Metadata</dt><dd className="mono" style={{ fontSize: 10 }}>{JSON.stringify(selectedNodeData.metadata, null, 1)}</dd></>
              )}
            </dl>
            <div className="draft-detail-edges">
              <span className="draft-detail-edges-title">Connections</span>
              {simEdges
                .filter((e) => e.source === selectedNode || e.target === selectedNode)
                .map((e, i) => {
                  const otherId = e.source === selectedNode ? e.target : e.source;
                  const otherNode = nodeMap.get(otherId);
                  const direction = e.source === selectedNode ? "→" : "←";
                  return (
                    <div key={i} className="draft-detail-edge-row" onClick={() => setSelectedNode(otherId)}>
                      <span className="draft-detail-edge-dir">{direction}</span>
                      <span className="draft-detail-edge-rel">{e.data.relation}</span>
                      <span className="draft-detail-edge-target">{otherId}</span>
                      {otherNode && (
                        <span className="draft-detail-edge-text">
                          {otherNode.data.text.slice(0, 40)}
                        </span>
                      )}
                    </div>
                  );
                })}
            </div>
          </div>
        </div>
      )}

      {/* Legend */}
      <div className="draft-legend">
        <span className="draft-legend-title">Node Types</span>
        <div className="draft-legend-items">
          {Object.entries(NODE_TYPE_COLORS).map(([type, color]) => (
            <div key={type} className="draft-legend-item">
              <span className="draft-legend-dot" style={{ background: color, boxShadow: `0 0 6px ${color}` }} />
              <span>{type}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
