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

const nodeTypes: NodeTypes = { character: CharacterNode };

function layoutNodes(graph: GraphData): Node[] {
  const count = graph.nodes.length;
  if (count === 0) return [];

  const cx = 300;
  const cy = 250;
  const radius = Math.max(120, count * 40);

  return graph.nodes.map((n, i) => {
    const angle = (2 * Math.PI * i) / count - Math.PI / 2;
    return {
      id: n.id,
      type: "character",
      position: {
        x: cx + radius * Math.cos(angle),
        y: cy + radius * Math.sin(angle),
      },
      data: {
        label: n.label,
        role: n.properties.role ?? "",
        description: n.properties.description ?? "",
      },
    };
  });
}

function buildEdges(graph: GraphData): Edge[] {
  return graph.edges.map((e, i) => ({
    id: `e-${i}-${e.source}-${e.target}`,
    source: e.source,
    target: e.target,
    label: e.relation,
    type: "default",
    animated: true,
    style: { stroke: "#94a3b8", strokeWidth: 1.5 },
    labelStyle: { fontSize: 11, fill: "#64748b" },
    markerEnd: { type: MarkerType.ArrowClosed, color: "#94a3b8" },
  }));
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

  return (
    <aside className="flex w-80 shrink-0 flex-col border-l border-slate-200 bg-white">
      <div className="border-b border-slate-100 px-5 py-3">
        <h2 className="text-sm font-semibold text-slate-700">人物关系图谱</h2>
        {hasData && (
          <p className="mt-0.5 text-[11px] text-slate-400">
            {graph.nodes.length} 人物 · {graph.edges.length} 关系
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
              <p className="text-sm font-medium text-slate-500">人物关系图谱</p>
              <p className="mt-1 text-xs text-slate-400">
                随着故事展开，人物关系将在此可视化呈现
              </p>
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}
