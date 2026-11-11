"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { ChangeEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "@/hooks/use-toast";
import {
  AlertCircle,
  FileSpreadsheet,
  FileText,
  FolderOpen,
  MoreHorizontal,
  Pencil,
  RefreshCw,
  Search,
  Trash2,
  Upload,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { AttachmentProgressRing } from "@/components/chat/attachment-progress-ring";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogClose,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
} from "@/components/ui/dropdown-menu";
import {
  deleteDocument,
  reingestDocument,
  renameDocument,
  subscribeToDocumentStatus,
  uploadDocument,
} from "@/lib/api";
import { ACCEPTED_DOCUMENT_EXTENSIONS } from "@/lib/types";
import type { DocumentRecord } from "@/lib/types";
import { useAuth } from "@/hooks/use-auth";
import { useDocuments } from "@/hooks/use-documents";

const SPREADSHEET_EXTENSIONS = new Set(["xlsx", "xls", "csv"]);

function fileIcon(filename: string, className: string) {
  const ext = filename.split(".").pop()?.toLowerCase() ?? "";
  return SPREADSHEET_EXTENSIONS.has(ext) ? (
    <FileSpreadsheet className={className} />
  ) : (
    <FileText className={className} />
  );
}

function DocumentCard({
  document,
  isOwnDocument,
  onRename,
  onDelete,
  onReingest,
}: {
  document: DocumentRecord;
  isOwnDocument: boolean;
  onRename: () => void;
  onDelete: () => void;
  onReingest: () => void;
}) {
  const isProcessing = document.status === "processing";
  const isFailed = document.status === "failed";

  return (
    <div className="group flex flex-col gap-3 rounded-xl border border-border bg-card/40 p-4 transition-colors hover:border-input hover:bg-accent/40">
      <div className="flex items-start justify-between gap-2">
        <div className="relative flex size-11 shrink-0 items-center justify-center rounded-lg bg-background">
          {fileIcon(
            document.filename,
            `size-5 ${isFailed ? "text-destructive" : "text-muted-foreground"}`,
          )}
          {isProcessing && (
            <AttachmentProgressRing
              indexed={document.chunks_indexed}
              total={document.chunks_total}
            />
          )}
        </div>
        {isOwnDocument && (
          <DropdownMenu>
            <DropdownMenuTrigger
              render={
                <Button
                  variant="ghost"
                  size="icon-sm"
                  className="opacity-0 transition-opacity group-hover:opacity-100"
                />
              }
            >
              <MoreHorizontal />
              <span className="sr-only">Document options</span>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem disabled={isProcessing} onClick={onReingest}>
                <RefreshCw />
                Re-ingest
              </DropdownMenuItem>
              <DropdownMenuItem disabled={isProcessing} onClick={onRename}>
                <Pencil />
                Rename
              </DropdownMenuItem>
              <DropdownMenuItem variant="destructive" disabled={isProcessing} onClick={onDelete}>
                <Trash2 />
                Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>

      <div className="min-w-0">
        <p className="line-clamp-2 text-sm font-medium leading-snug">{document.filename}</p>
        <div className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
          {isFailed ? (
            <span className="flex items-center gap-1 text-destructive">
              <AlertCircle className="size-3" />
              Couldn&apos;t index
            </span>
          ) : isProcessing ? (
            <span>
              Indexing {document.chunks_indexed}/{document.chunks_total || "…"}
            </span>
          ) : (
            <span>{document.chunk_count} chunks</span>
          )}
        </div>
      </div>

      <div className="mt-auto flex items-center gap-1.5">
        {!isOwnDocument && (
          <Badge variant="outline" className="text-[10px]">
            Shared
          </Badge>
        )}
        <span className="text-[11px] text-muted-foreground">
          {new Date(document.ingested_at).toLocaleDateString()}
        </span>
      </div>
    </div>
  );
}

function DocumentCardSkeleton() {
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-card/40 p-4">
      <Skeleton className="size-11 rounded-lg" />
      <div className="flex flex-col gap-1.5">
        <Skeleton className="h-3.5 w-4/5 rounded-full" />
        <Skeleton className="h-3 w-1/2 rounded-full" />
      </div>
      <Skeleton className="h-3 w-16 rounded-full" />
    </div>
  );
}

export default function DocumentsPage() {
  const router = useRouter();
  const { session, isLoading: isAuthLoading } = useAuth();
  const { documents, isLoading, refresh, update, remove, add } = useDocuments();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const statusUnsubscribes = useRef<Record<string, () => void>>({});

  const [query, setQuery] = useState("");
  const [renameTarget, setRenameTarget] = useState<DocumentRecord | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<DocumentRecord | null>(null);

  useEffect(() => {
    if (!isAuthLoading && !session) {
      router.replace("/sign-in");
    }
  }, [isAuthLoading, session, router]);

  useEffect(() => {
    if (!session) return;
    refresh();
  }, [session, refresh]);

  useEffect(() => {
    const unsubscribes = statusUnsubscribes.current;
    return () => {
      Object.values(unsubscribes).forEach((unsubscribe) => unsubscribe());
    };
  }, []);

  // Shared by both the upload button and re-ingest: watches a doc_id's
  // status over SSE (same stream the chat composer's attachment chips
  // use) and re-syncs the whole list from the server once it reaches a
  // terminal state - simpler and more robust than hand-patching every
  // field a fresh ingest can change (chunk_count, embedding_model, etc.).
  function watchUntilTerminal(docId: string, onFailed: () => void) {
    statusUnsubscribes.current[docId] = subscribeToDocumentStatus(docId, (status) => {
      if (status.status === "ready") {
        delete statusUnsubscribes.current[docId];
        refresh();
      } else if (status.status === "failed") {
        delete statusUnsubscribes.current[docId];
        onFailed();
        refresh();
      } else {
        update(docId, { chunks_indexed: status.chunks_indexed, chunks_total: status.chunks_total });
      }
    });
  }

  async function handleFileSelected(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

    try {
      const { docId, status } = await uploadDocument(file);
      if (status === "ready") {
        toast.success(`"${file.name}" is already indexed - nothing to do.`);
        return;
      }
      add({
        doc_id: docId,
        filename: file.name,
        file_hash: "",
        ingested_at: new Date().toISOString(),
        node_count: 0,
        chunk_count: 0,
        embedding_model: null,
        user_id: session?.user.id ?? null,
        status: "processing",
        chunks_indexed: 0,
        chunks_total: 0,
      });
      watchUntilTerminal(docId, () => toast.error(`Couldn't index "${file.name}".`));
    } catch {
      toast.error(`Couldn't upload "${file.name}".`);
    }
  }

  function openRename(document: DocumentRecord) {
    setRenameTarget(document);
    setRenameValue(document.filename);
  }

  async function submitRename() {
    if (!renameTarget) return;
    const filename = renameValue.trim();
    if (!filename || filename === renameTarget.filename) {
      setRenameTarget(null);
      return;
    }
    const target = renameTarget;
    const previousFilename = target.filename;
    update(target.doc_id, { filename });
    setRenameTarget(null);
    try {
      await renameDocument(target.doc_id, filename);
    } catch {
      update(target.doc_id, { filename: previousFilename });
      toast.error("Couldn't rename this document - the name may already be in use.");
    }
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    const target = deleteTarget;
    remove(target.doc_id);
    setDeleteTarget(null);
    try {
      await deleteDocument(target.doc_id);
    } catch {
      toast.error("Couldn't delete this document.");
      refresh();
    }
  }

  async function handleReingest(document: DocumentRecord) {
    update(document.doc_id, { status: "processing" });
    try {
      const { docId } = await reingestDocument(document.doc_id);
      watchUntilTerminal(docId, () => toast.error(`Couldn't re-index "${document.filename}".`));
    } catch {
      toast.error(`Couldn't re-index "${document.filename}".`);
      refresh();
    }
  }

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return documents;
    return documents.filter((d) => d.filename.toLowerCase().includes(q));
  }, [documents, query]);

  return (
    <div className="flex h-full flex-1 flex-col">
      <header className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
        <div className="min-w-0">
          <h1 className="font-heading text-sm font-semibold">Library</h1>
          <p className="truncate text-xs text-muted-foreground">
            Your uploads plus the shared demo corpus, available to every signed-in user.
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPTED_DOCUMENT_EXTENSIONS}
            className="hidden"
            onChange={handleFileSelected}
          />
          <Button size="sm" onClick={() => fileInputRef.current?.click()}>
            <Upload />
            Upload
          </Button>
          <Link href="/" className="text-xs text-muted-foreground hover:text-foreground">
            Back to chat
          </Link>
        </div>
      </header>

      <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-4 overflow-y-auto p-4">
        {documents.length > 0 && (
          <div className="relative">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search your documents…"
              className="pl-8"
            />
          </div>
        )}

        {isLoading ? (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <DocumentCardSkeleton key={i} />
            ))}
          </div>
        ) : documents.length === 0 ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 py-10 text-center">
            <div className="flex size-12 items-center justify-center rounded-xl bg-muted">
              <FolderOpen className="size-5 text-muted-foreground" />
            </div>
            <div>
              <p className="text-sm font-medium">No documents yet</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Upload one to start chatting about it.
              </p>
            </div>
          </div>
        ) : filtered.length === 0 ? (
          <p className="py-10 text-center text-sm text-muted-foreground">
            No documents match &quot;{query}&quot;.
          </p>
        ) : (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            {filtered.map((document) => (
              <DocumentCard
                key={document.doc_id}
                document={document}
                isOwnDocument={document.user_id === session?.user.id}
                onRename={() => openRename(document)}
                onDelete={() => setDeleteTarget(document)}
                onReingest={() => handleReingest(document)}
              />
            ))}
          </div>
        )}
      </div>

      <Dialog open={!!renameTarget} onOpenChange={(open) => !open && setRenameTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rename this document</DialogTitle>
          </DialogHeader>
          <Input
            value={renameValue}
            onChange={(event) => setRenameValue(event.target.value)}
            onKeyDown={(event) => event.key === "Enter" && submitRename()}
            autoFocus
          />
          <DialogFooter>
            <DialogClose render={<Button variant="outline" />}>Cancel</DialogClose>
            <Button onClick={submitRename} disabled={!renameValue.trim()}>
              Rename
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete this document?</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            {`"${deleteTarget?.filename}" and its indexed content will be permanently deleted. Conversations that already reference it will keep working, just without this source.`}
          </p>
          <DialogFooter>
            <DialogClose render={<Button variant="outline" />}>Cancel</DialogClose>
            <Button variant="destructive" onClick={confirmDelete}>
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
