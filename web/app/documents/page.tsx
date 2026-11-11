"use client";

import { useEffect, useRef, useState } from "react";
import type { ChangeEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "@/hooks/use-toast";
import { FileText, MoreHorizontal, Pencil, RefreshCw, Trash2, Upload } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
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

function statusBadge(status: DocumentRecord["status"]) {
  if (status === "processing") return <Badge variant="secondary">Processing…</Badge>;
  if (status === "failed") return <Badge variant="destructive">Failed</Badge>;
  return null;
}

export default function DocumentsPage() {
  const router = useRouter();
  const { session, isLoading: isAuthLoading } = useAuth();
  const { documents, isLoading, refresh, update, remove, add } = useDocuments();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const statusUnsubscribes = useRef<Record<string, () => void>>({});

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

  return (
    <div className="flex h-full flex-1 flex-col">
      <header className="flex items-center justify-between border-b border-border px-4 py-3">
        <div>
          <h1 className="text-sm font-semibold">Documents</h1>
          <p className="text-xs text-muted-foreground">
            Your uploads plus the shared demo corpus, available to every signed-in user.
          </p>
        </div>
        <div className="flex items-center gap-3">
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

      <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-2 overflow-y-auto p-4">
        {isLoading ? (
          Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-14 w-full" />)
        ) : documents.length === 0 ? (
          <p className="py-10 text-center text-sm text-muted-foreground">
            No documents yet - upload one to get started.
          </p>
        ) : (
          documents.map((document) => {
            const isOwnDocument = document.user_id === session?.user.id;
            const isBusy = document.status === "processing";
            return (
              <div
                key={document.doc_id}
                className="flex items-center gap-3 rounded-lg border border-border px-3 py-2.5"
              >
                <FileText className="size-4 shrink-0 text-muted-foreground" />
                <div className="flex-1 overflow-hidden">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-medium">{document.filename}</span>
                    {statusBadge(document.status)}
                    {!isOwnDocument && <Badge variant="outline">Shared</Badge>}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {document.chunk_count} chunks ·{" "}
                    {new Date(document.ingested_at).toLocaleDateString()}
                  </p>
                </div>
                {isOwnDocument && (
                  <DropdownMenu>
                    <DropdownMenuTrigger render={<Button variant="ghost" size="icon-sm" />}>
                      <MoreHorizontal />
                      <span className="sr-only">Document options</span>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem disabled={isBusy} onClick={() => handleReingest(document)}>
                        <RefreshCw />
                        Re-ingest
                      </DropdownMenuItem>
                      <DropdownMenuItem disabled={isBusy} onClick={() => openRename(document)}>
                        <Pencil />
                        Rename
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        variant="destructive"
                        disabled={isBusy}
                        onClick={() => setDeleteTarget(document)}
                      >
                        <Trash2 />
                        Delete
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                )}
              </div>
            );
          })
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
