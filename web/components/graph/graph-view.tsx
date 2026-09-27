"use client";

import { useEffect, useRef } from "react";
import { DataSet } from "vis-data";
import { Network } from "vis-network";
import type { GraphData } from "@/lib/types";

type GraphViewProps = {
  data: GraphData;
  onNodeClick: (entityId: number) => void;
};

export function GraphView({ data, onNodeClick }: GraphViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const networkRef = useRef<Network | null>(null);
  const onNodeClickRef = useRef(onNodeClick);
  onNodeClickRef.current = onNodeClick;

  useEffect(() => {
    if (!containerRef.current) return;

    const nodes = new DataSet(
      data.nodes.map((node) => ({ id: node.id, label: node.label }))
    );
    const edges = new DataSet(
      data.edges.map((edge, index) => ({
        id: index,
        from: edge.from,
        to: edge.to,
        value: edge.weight,
      }))
    );

    const network = new Network(
      containerRef.current,
      { nodes, edges },
      {
        nodes: {
          shape: "dot",
          size: 10,
          font: { color: "var(--foreground)", size: 12 },
          color: {
            background: "var(--primary)",
            border: "var(--primary)",
            highlight: { background: "var(--primary)", border: "var(--foreground)" },
          },
        },
        edges: {
          color: { color: "var(--border)", highlight: "var(--foreground)" },
          smooth: false,
          scaling: { min: 1, max: 6 },
        },
        physics: {
          solver: "forceAtlas2Based",
          forceAtlas2Based: { gravitationalConstant: -50, springLength: 100 },
          stabilization: { iterations: 150 },
        },
        interaction: { hover: true },
      }
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
