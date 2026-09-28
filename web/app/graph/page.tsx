"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { GraphView } from "@/components/graph/graph-view";
import { Skeleton } from "@/components/ui/skeleton";
import { getDocuments, getGraphData, getGraphSection } from "@/lib/api";
import { useAuth } from "@/hooks/use-auth";
import type { DocumentRecord, GraphData, GraphSection } from "@/lib/types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export default function GraphPage() {
  const router = useRouter();
  const { session, isLoading: isAuthLoading } = useAuth();

  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [selectedDocId, setSelectedDocId] = useState<string>("");
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedSection, setSelectedSection] = useState<GraphSection | null>(null);
  const [selectedLabel, setSelectedLabel] = useState<string>("");

  useEffect(() => {
    if (!isAuthLoading && !session) {
      router.replace("/sign-in");
    }
  }, [isAuthLoading, session, router]);

  useEffect(() => {
    if (!session) return;
    getDocuments()
      .then(setDocuments)
      .catch(() => {
        // Filter dropdown just stays empty (full-corpus view still works) -
        // not worth a separate error state for a non-critical control.
      });
  }, [session]);

  useEffect(() => {
    if (!session) return;
    setIsLoading(true);
    setError(null);
    setSelectedSection(null);
    getGraphData(selectedDocId || undefined)
      .then(setGraphData)
      .catch(() => {
        setError("Couldn't load the entity graph.");
        toast.error("Couldn't load the entity graph.");
      })
      .finally(() => setIsLoading(false));
  }, [selectedDocId, session]);

  async function handleNodeClick(entityId: number) {
    const node = graphData?.nodes.find((n) => n.id === entityId);
    if (!node) return;
    setSelectedLabel(node.label);
    setSelectedSection(null);
    try {
      const section = await getGraphSection(node.node_id);
      setSelectedSection(section);
    } catch {
      setSelectedSection(null);
    }
  }

  const selectedDoc = selectedSection
    ? documents.find((doc) => doc.doc_id === selectedSection.doc_id)
    : undefined;

  if (isAuthLoading || !session) {
    return (
      <div className="flex flex-1 flex-col gap-4 p-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-full w-full" />
      </div>
    );
  }

  return (
    <div className="flex h-full flex-1 flex-col">
      <header className="flex items-center justify-between border-b border-border px-4 py-3">
        <div>
          <h1 className="text-sm font-semibold">Entity Graph</h1>
          <p className="text-xs text-muted-foreground">
            Co-occurring technical entities extracted from indexed documents.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={selectedDocId}
            onChange={(event) => setSelectedDocId(event.target.value)}
            className="h-8 rounded-lg border border-input bg-background px-2 text-xs outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
          >
            <option value="">All documents</option>
            {documents.map((doc) => (
              <option key={doc.doc_id} value={doc.doc_id}>
                {doc.filename}
              </option>
            ))}
          </select>
          <Link
            href="/"
            className="text-xs text-muted-foreground hover:text-foreground"
          >
            Back to chat
          </Link>
        </div>
      </header>

      <div className="relative flex flex-1 overflow-hidden">
        <div className="flex-1">
          {isLoading ? (
            <div className="flex h-full flex-col gap-3 p-6">
              <Skeleton className="h-full w-full" />
            </div>
          ) : error ? (
            <p className="p-6 text-sm text-destructive">{error}</p>
          ) : !graphData || graphData.nodes.length === 0 ? (
            <p className="p-6 text-sm text-muted-foreground">
              No entities indexed yet. Enable{" "}
              <code className="rounded bg-muted px-1 py-0.5">
                ENABLE_ENTITY_GRAPH
              </code>{" "}
              in the server and re-ingest documents to populate this graph.
            </p>
          ) : (
            <GraphView data={graphData} onNodeClick={handleNodeClick} />
          )}
        </div>

        {selectedLabel && (
          <aside className="w-80 shrink-0 overflow-y-auto border-l border-border p-4">
            <div className="flex items-start justify-between gap-2">
              <h2 className="text-sm font-semibold">{selectedLabel}</h2>
              <button
                onClick={() => setSelectedLabel("")}
                className="text-xs text-muted-foreground hover:text-foreground"
              >
                Close
              </button>
            </div>

            {!selectedSection ? (
              <div className="mt-3 flex flex-col gap-2">
                <Skeleton className="h-4 w-1/2" />
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-16 w-full" />
              </div>
            ) : (
              <div className="mt-3 flex flex-col gap-2 text-xs">
                {selectedDoc && (
                  <p className="text-muted-foreground">
                    Document: <span className="text-foreground">{selectedDoc.filename}</span>
                  </p>
                )}
                {selectedSection.heading_path && (
                  <p className="text-muted-foreground">
                    Section: <span className="text-foreground">{selectedSection.heading_path}</span>
                  </p>
                )}
                {selectedSection.content && (
                  <p className="mt-1 whitespace-pre-wrap rounded-lg border border-border bg-muted/30 p-2 text-foreground">
                    {selectedSection.content}
                  </p>
                )}
                {selectedDoc && (
                  <a
                    href={`${API_BASE_URL}/source/${encodeURIComponent(selectedDoc.filename)}${
                      selectedSection.page ? `#page=${selectedSection.page}` : ""
                    }`}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-1 text-primary hover:underline"
                  >
                    Open source document
                    {selectedSection.page ? ` (page ${selectedSection.page})` : ""}
                  </a>
                )}
              </div>
            )}
          </aside>
        )}
      </div>
    </div>
  );
}
