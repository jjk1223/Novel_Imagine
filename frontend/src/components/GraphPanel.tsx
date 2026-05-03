"use client";

import { useEffect } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  MarkerType,
  type NodeTypes,
  Handle,
  Position,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { GraphData } from "@/lib/api";

interface Props {
  graph: GraphData;
}

function CharacterNode({ data }: { data: { label: string; role: string; description: string } }) {
  const roleColors: Record<string, string> = {
    "主角": "bg-indigo-100 border-indigo-300 text-indigo-800",
    "配角": "bg-slate-100 border-slate-300 text-slate-700",
    "反派": "bg-red-50 border-red-200 text-red-700",
  };
  const cls = roleColors[data.role] ?? "bg-white border-slate-200 text-slate-700";

  return (
    <div className={`rounded-xl border-2 px-4 py-2.5 shadow-sm ${cls}`}>
      <Handle type="target" position={Position.Top} className="!bg-slate-400" />
      <div className="text-center">
        <div className="text-sm font-semibold">{data.label}</div>
        {data.role && (
          <div className="mt-0.5 text-[10px] opacity-60">{data.role}</div>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-slate-400" />
    </div>
  );
}

function EventNode({ data }: { data: { label: string; time: string; significance: string } }) {
  const sigColors: Record<string, string> = {
    "高": "bg-amber-100 border-amber-300 text-amber-800",
    "中": "bg-yellow-50 border-yellow-200 text-yellow-700",
    "低": "bg-stone-50 border-stone-200 text-stone-600",
  };
  const cls = sigColors[data.significance] ?? "bg-yellow-50 border-yellow-200 text-yellow-700";

  return (
    <div className={`rounded-lg border-2 px-3 py-2 shadow-sm ${cls}`}>
      <Handle type="target" position={Position.Top} className="!bg-amber-400" />
      <div className="text-center">
        <div className="text-[11px] font-semibold">{data.label}</div>
        {data.time && <div className="text-[9px] opacity-60">{data.time}</div>}
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-amber-400" />
    </div>
  );
}

function ItemNode({ data }: { data: { label: string; category: string; owner: string } }) {
  const catColors: Record<string, string> = {
    "武器": "bg-red-50 border-red-200 text-red-700",
    "信物": "bg-pink-50 border-pink-200 text-pink-700",
    "法宝": "bg-purple-50 border-purple-200 text-purple-700",
    "文件": "bg-sky-50 border-sky-200 text-sky-700",
  };
  const cls = catColors[data.category] ?? "bg-teal-50 border-teal-200 text-teal-700";

  return (
    <div className={`rounded-md border-2 px-3 py-2 shadow-sm ${cls}`}>
      <Handle type="target" position={Position.Top} className="!bg-teal-400" />
      <div className="text-center">
        <div className="text-[11px] font-semibold">{data.label}</div>
        {data.category && <div className="text-[9px] opacity-60">{data.category}</div>}
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-teal-400" />
    </div>
  );
}

const nodeTypes: NodeTypes = {
  character: CharacterNode,
  event: EventNode,
  item: ItemNode,
};

function layoutNodes(graph: GraphData): Node[] {
  const count = graph.nodes.length;
  if (count === 0) return [];

  const cx = 300;
  const cy = 250;
  const radius = Math.max(120, count * 40);

  return graph.nodes.map((n, i) => {
    const angle = (2 * Math.PI * i) / count - Math.PI / 2;
    const nodeType = n.type || "character";
    return {
      id: n.id,
      type: nodeType,
      position: {
        x: cx + radius * Math.cos(angle),
        y: cy + radius * Math.sin(angle),
      },
      data: {
        label: n.label,
        role: n.properties.role ?? "",
        description: n.properties.description ?? "",
        time: n.properties.time ?? "",
        significance: n.properties.significance ?? "",
        category: n.properties.category ?? "",
        owner: n.properties.owner ?? "",
      },
    };
  });
}

const edgeStyleMap: Record<string, { stroke: string; dash: string; animated: boolean }> = {
  relation: { stroke: "#94a3b8", dash: "", animated: false },
  participates: { stroke: "#f59e0b", dash: "5,5", animated: false },
  possesses: { stroke: "#14b8a6", dash: "3,3", animated: false },
  triggers: { stroke: "#ef4444", dash: "8,4", animated: true },
  appears_in: { stroke: "#8b5cf6", dash: "2,2", animated: false },
};

function buildEdges(graph: GraphData): Edge[] {
  return graph.edges.map((e, i) => {
    const style = edgeStyleMap[e.type] ?? edgeStyleMap.relation;
    return {
      id: `e-${i}-${e.source}-${e.target}`,
      source: e.source,
      target: e.target,
      label: e.relation,
      type: "default",
      animated: style.animated,
      style: { stroke: style.stroke, strokeWidth: 1.5, strokeDasharray: style.dash || undefined },
      labelStyle: { fontSize: 10, fill: style.stroke },
      markerEnd: { type: MarkerType.ArrowClosed, color: style.stroke },
    };
  });
}

export default function GraphPanel({ graph }: Props) {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  useEffect(() => {
    if (graph.nodes.length > 0) {
      setNodes(layoutNodes(graph));
      setEdges(buildEdges(graph));
    }
  }, [graph, setNodes, setEdges]);

  const hasData = graph.nodes.length > 0;
  const charCount = graph.nodes.filter((n) => n.type === "character" || !n.type).length;
  const eventCount = graph.nodes.filter((n) => n.type === "event").length;
  const itemCount = graph.nodes.filter((n) => n.type === "item").length;

  return (
    <aside className="flex w-80 shrink-0 flex-col border-l border-slate-200 bg-white">
      <div className="border-b border-slate-100 px-5 py-3">
        <h2 className="text-sm font-semibold text-slate-700">故事图谱</h2>
        {hasData && (
          <p className="mt-0.5 text-[11px] text-slate-400">
            {graph.nodes.length} 实体 · {graph.edges.length} 关系
            {charCount > 0 && ` (人物${charCount}`}
            {eventCount > 0 && `${charCount > 0 ? "，" : " (事件"}${eventCount}`}
            {itemCount > 0 && `${(charCount > 0 || eventCount > 0) ? "，" : " (物品"}${itemCount}`}
            {(charCount > 0 || eventCount > 0 || itemCount > 0) && ")"}
          </p>
        )}
      </div>

      <div className="relative flex-1">
        {hasData ? (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            nodeTypes={nodeTypes}
            fitView
            fitViewOptions={{ padding: 0.3 }}
            minZoom={0.3}
            maxZoom={2}
            proOptions={{ hideAttribution: true }}
          >
            <Background gap={20} size={1} color="#f1f5f9" />
            <Controls
              showInteractive={false}
              className="!border-slate-200 !shadow-sm [&>button]:!border-slate-200 [&>button]:!bg-white"
            />
          </ReactFlow>
        ) : (
          <div className="flex h-full items-center justify-center p-5">
            <div className="text-center">
              <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-indigo-50">
                <svg
                  className="h-8 w-8 text-indigo-400"
                  fill="none"
                  viewBox="0 0 24 24"
                  strokeWidth={1.5}
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M7.5 21L3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5"
                  />
                </svg>
              </div>
              <p className="text-sm font-medium text-slate-500">故事图谱</p>
              <p className="mt-1 text-xs text-slate-400">
                人物、事件、物品关系将在此可视化呈现
              </p>
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}
