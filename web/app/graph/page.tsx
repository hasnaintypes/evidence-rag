"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "@/hooks/use-toast";
import { Network, Share2 } from "lucide-react";
import { GraphView } from "@/components/graph/graph-view";
import { MessageResponse } from "@/components/ai-elements/message";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { getDocuments, getGraphData, getGraphSection } from "@/lib/api";
import { useAuth } from "@/hooks/use-auth";
import type { DocumentRecord, GraphData, GraphSection } from "@/lib/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
const ALL_DOCS = "all";

export default function GraphPage() {
  const router = useRouter();
  const { session, isLoading: isAuthLoading } = useAuth();

  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [selectedDocId, setSelectedDocId] = useState<string>(ALL_DOCS);
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [panelOpen, setPanelOpen] = useState(false);
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
    // Resetting loading/error/selection state when selectedDocId changes,
    // before kicking off the new fetch below, is the standard
    // fetch-on-param-change pattern - there's no external store to
    // subscribe to here instead (unlike the carousel-style effects
    // elsewhere in this codebase, which use useSyncExternalStore).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setIsLoading(true);
    setError(null);
    setPanelOpen(false);
    const docId = selectedDocId === ALL_DOCS ? undefined : selectedDocId;
    getGraphData(docId)
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
    setPanelOpen(true);
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

  return (
    <div className="flex h-full flex-1 flex-col">
      <header className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
        <div className="min-w-0">
          <h1 className="font-heading text-sm font-semibold">Entity Graph</h1>
          <p className="truncate text-xs text-muted-foreground">
            Co-occurring technical entities extracted from indexed documents.
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          <Select
            value={selectedDocId}
            onValueChange={(value) => setSelectedDocId(value ?? ALL_DOCS)}
          >
            <SelectTrigger size="sm" className="w-44">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL_DOCS}>All documents</SelectItem>
              {documents.map((doc) => (
                <SelectItem key={doc.doc_id} value={doc.doc_id}>
                  {doc.filename}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </header>

      <div className="relative flex-1 overflow-hidden">
        {isLoading ? (
          <div className="flex h-full items-center justify-center">
            <div className="flex flex-col items-center gap-3">
              <Share2 className="size-6 animate-pulse text-muted-foreground" />
              <p className="text-xs text-muted-foreground">Loading the entity graph…</p>
            </div>
          </div>
        ) : error ? (
          <div className="flex h-full items-center justify-center p-6">
            <p className="text-sm text-destructive">{error}</p>
          </div>
        ) : !graphData || graphData.nodes.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
            <div className="flex size-12 items-center justify-center rounded-xl bg-muted">
              <Network className="size-5 text-muted-foreground" />
            </div>
            <div>
              <p className="text-sm font-medium">No entities indexed yet</p>
              <p className="mt-1 max-w-sm text-xs text-muted-foreground">
                Enable <code className="rounded bg-muted px-1 py-0.5">ENABLE_ENTITY_GRAPH</code> on
                the server and re-ingest documents to populate this graph.
              </p>
            </div>
          </div>
        ) : (
          <GraphView data={graphData} onNodeClick={handleNodeClick} />
        )}
      </div>

      <Sheet open={panelOpen} onOpenChange={setPanelOpen}>
        <SheetContent className="flex flex-col gap-0 p-0 sm:max-w-md">
          <SheetHeader className="border-b border-border">
            <SheetTitle>{selectedLabel}</SheetTitle>
            {selectedDoc && (
              <SheetDescription>
                {selectedDoc.filename}
                {selectedSection?.heading_path ? ` · ${selectedSection.heading_path}` : ""}
              </SheetDescription>
            )}
          </SheetHeader>
          <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-4">
            {!selectedSection ? (
              <div className="flex flex-col gap-2">
                <Skeleton className="h-3.5 w-3/4 rounded-full" />
                <Skeleton className="h-3.5 w-full rounded-full" />
                <Skeleton className="h-3.5 w-5/6 rounded-full" />
                <Skeleton className="h-3.5 w-2/3 rounded-full" />
              </div>
            ) : (
              <>
                {selectedSection.content && (
                  <blockquote className="border-l-2 border-muted pl-3 text-sm leading-relaxed text-muted-foreground [&_*]:my-0">
                    <MessageResponse>{selectedSection.content}</MessageResponse>
                  </blockquote>
                )}
                {selectedDoc && (
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-fit"
                    nativeButton={false}
                    render={
                      <a
                        href={`${API_BASE_URL}/source/${encodeURIComponent(selectedDoc.filename)}?token=${encodeURIComponent(
                          selectedSection.source_token,
                        )}${selectedSection.page ? `#page=${selectedSection.page}` : ""}`}
                        target="_blank"
                        rel="noreferrer"
                      />
                    }
                  >
                    Open source document
                    {selectedSection.page ? ` (page ${selectedSection.page})` : ""}
                  </Button>
                )}
              </>
            )}
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}
