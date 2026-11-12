"use client";

import { useEffect, useRef } from "react";
import { DataSet } from "vis-data";
import { Network } from "vis-network";
import type { GraphData } from "@/lib/types";

type GraphViewProps = {
  data: GraphData;
  onNodeClick: (entityId: number) => void;
};

// vis-network draws to a <canvas> - its color options become a 2D context
// fillStyle/strokeStyle directly, which (unlike a DOM element's CSS) can't
// resolve a raw "var(--foo)" string. Reads the actual computed value of a
// custom property instead - a real color token is a perfectly valid
// canvas fillStyle (oklch() included, in any current browser), it just
// has to be resolved first.
function cssVar(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

export function GraphView({ data, onNodeClick }: GraphViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const networkRef = useRef<Network | null>(null);
  const onNodeClickRef = useRef(onNodeClick);

  useEffect(() => {
    onNodeClickRef.current = onNodeClick;
  }, [onNodeClick]);

  useEffect(() => {
    if (!containerRef.current) return;

    const nodes = new DataSet(data.nodes.map((node) => ({ id: node.id, label: node.label })));
    const edges = new DataSet(
      data.edges.map((edge, index) => ({
        id: index,
        from: edge.from,
        to: edge.to,
        value: edge.weight,
      })),
    );

    const accent = cssVar("--sidebar-primary", "#6d8cff");
    const foreground = cssVar("--foreground", "#f5f5f5");
    const border = cssVar("--border", "#3a3a3a");
    const mutedForeground = cssVar("--muted-foreground", "#a0a0a0");

    const network = new Network(
      containerRef.current,
      { nodes, edges },
      {
        nodes: {
          shape: "dot",
          size: 10,
          font: { color: foreground, size: 12 },
          color: {
            background: accent,
            border: accent,
            highlight: { background: accent, border: foreground },
          },
        },
        edges: {
          color: { color: border, highlight: accent, hover: mutedForeground },
          smooth: false,
          scaling: { min: 1, max: 6 },
        },
        physics: {
          solver: "forceAtlas2Based",
          forceAtlas2Based: { gravitationalConstant: -50, springLength: 100 },
          stabilization: { iterations: 150 },
        },
        interaction: { hover: true },
      },
    );

    network.on("click", (params) => {
      if (params.nodes.length > 0) {
        onNodeClickRef.current(params.nodes[0] as number);
      }
    });

    networkRef.current = network;
    return () => {
      network.destroy();
      networkRef.current = null;
    };
  }, [data]);

  return <div ref={containerRef} className="h-full w-full" />;
}
