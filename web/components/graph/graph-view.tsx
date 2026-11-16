"use client";

import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import { DataSet } from "vis-data";
import { Network, type Edge, type Node } from "vis-network";
import type { GraphData } from "@/lib/types";
import { colorForDocId, distinctDocIds } from "@/lib/graph-colors";

export type GraphViewHandle = {
  reset: () => void;
};

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

export const GraphView = forwardRef<GraphViewHandle, GraphViewProps>(function GraphView(
  { data, onNodeClick },
  ref,
) {
  const containerRef = useRef<HTMLDivElement>(null);
  const networkRef = useRef<Network | null>(null);
  const onNodeClickRef = useRef(onNodeClick);

  useImperativeHandle(ref, () => ({
    reset: () => {
      const network = networkRef.current;
      if (!network) return;
      network.unselectAll();
      network.fit({ animation: { duration: 300, easingFunction: "easeInOutQuad" } });
    },
  }));

  useEffect(() => {
    onNodeClickRef.current = onNodeClick;
  }, [onNodeClick]);

  useEffect(() => {
    if (!containerRef.current) return;

    const foreground = cssVar("--foreground", "#f5f5f5");
    const mutedForeground = cssVar("--muted-foreground", "#a0a0a0");
    const borderStrong = cssVar("--border-strong", cssVar("--border", "#3a3a3a"));
    const background = cssVar("--background", "#0a0a0a");

    // Degree (how many other entities a node co-occurs with) is the one
    // real signal of "importance" this data has - vis-network's built-in
    // value-based scaling turns that into node size directly, same
    // reasoning as coloring by document: real data, not a fabricated metric.
    const degreeByNodeId = new Map<number, number>();
    data.edges.forEach((edge) => {
      degreeByNodeId.set(edge.from, (degreeByNodeId.get(edge.from) ?? 0) + 1);
      degreeByNodeId.set(edge.to, (degreeByNodeId.get(edge.to) ?? 0) + 1);
    });

    const allDocIds = distinctDocIds(data.nodes.map((n) => n.doc_id));

    const nodes = new DataSet<Node>(
      data.nodes.map((node) => {
        const color = colorForDocId(node.doc_id, allDocIds);
        return {
          id: node.id,
          label: node.label,
          value: degreeByNodeId.get(node.id) ?? 0,
          color: {
            background: color,
            border: borderStrong,
            highlight: { background: color, border: foreground },
          },
        };
      }),
    );
    const edges = new DataSet<Edge>(
      data.edges.map((edge, index) => ({
        id: index,
        from: edge.from,
        to: edge.to,
        value: edge.weight,
      })),
    );

    const network = new Network(
      containerRef.current,
      { nodes, edges },
      {
        nodes: {
          shape: "dot",
          scaling: { min: 12, max: 34 },
          font: { color: foreground, size: 12 },
          borderWidth: 1.5,
        },
        edges: {
          color: { color: borderStrong, highlight: foreground, hover: mutedForeground },
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

    // Selection dims everything not connected to the clicked node, same
    // visual language as the design preview's gnode/glink "dimmed" classes.
    function dimTo(connectedNodeIds: Set<number> | null) {
      nodes.forEach((node) => {
        const isDimmed = connectedNodeIds !== null && !connectedNodeIds.has(node.id as number);
        nodes.update({ id: node.id, opacity: isDimmed ? 0.25 : 1 });
      });
      edges.forEach((edge) => {
        const isDimmed =
          connectedNodeIds !== null &&
          !(connectedNodeIds.has(edge.from as number) && connectedNodeIds.has(edge.to as number));
        // vis-data's DataSet.update() replaces an item's entire `color`
        // field wholesale rather than merging it into the network-level
        // default (`edges.color` above, which also sets highlight/hover) -
        // once an edge gets a per-item color override here, omitting
        // highlight/hover would silently drop them for that edge's
        // remaining lifetime (including after dimTo(null) "restores" it -
        // that call still only sets `color`, so the loss would otherwise
        // be permanent, not just while dimmed). Always include all three
        // so an edge never loses its hover/highlight behavior.
        edges.update({
          id: edge.id,
          color: {
            color: isDimmed ? background : borderStrong,
            highlight: foreground,
            hover: mutedForeground,
          },
        });
      });
    }

    network.on("selectNode", (params) => {
      const selectedId = params.nodes[0] as number;
      const connectedNodeIds = network.getConnectedNodes(selectedId) as number[];
      const connected = new Set<number>([selectedId, ...connectedNodeIds]);
      dimTo(connected);
      if (params.nodes.length > 0) onNodeClickRef.current(selectedId);
    });
    network.on("deselectNode", () => dimTo(null));

    networkRef.current = network;
    return () => {
      network.destroy();
      networkRef.current = null;
    };
  }, [data]);

  return <div ref={containerRef} className="h-full w-full" />;
});
