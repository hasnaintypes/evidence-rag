"use client";

import { useEffect, useState } from "react";
import { FileTextIcon, FolderOpenIcon } from "lucide-react";
import { PromptInputButton } from "@/components/ai-elements/prompt-input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { getDocuments } from "@/lib/api";
import type { DocumentRecord } from "@/lib/types";

// Lets a brand-new chat start against documents that are already indexed
// (the shared/demo corpus, or anything this user uploaded earlier via the
// Documents page) instead of forcing a fresh upload every time - GET
// /documents already returns exactly that set (see
// list_documents()'s docstring: "a user's own uploaded documents plus
// shared/demo documents"), this just finally surfaces it here.
export function AttachExistingDocumentPicker({
  excludeDocIds,
  disabled,
  onSelect,
}: {
  excludeDocIds: string[];
  disabled?: boolean;
  onSelect: (doc: DocumentRecord) => void;
}) {
  const [open, setOpen] = useState(false);
  const [documents, setDocuments] = useState<DocumentRecord[] | null>(null);

  useEffect(() => {
    if (!open || documents !== null) return;
    getDocuments()
      .then(setDocuments)
      .catch(() => setDocuments([]));
  }, [open, documents]);

  const excluded = new Set(excludeDocIds);
  const available = (documents ?? []).filter(
    (doc) => doc.status === "ready" && !excluded.has(doc.doc_id),
  );

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        render={
          <PromptInputButton
            type="button"
            disabled={disabled}
            tooltip="Attach an existing document"
          >
            <FolderOpenIcon className="size-4" />
          </PromptInputButton>
        }
      />
      <PopoverContent align="start" className="w-80 p-0">
        <Command>
          <CommandInput placeholder="Search your documents…" />
          <CommandList>
            {documents === null ? (
              <div className="p-4 text-center text-sm text-muted-foreground">Loading…</div>
            ) : (
              <>
                <CommandEmpty>
                  {documents.length === 0
                    ? "No documents indexed yet - upload one from the Library page."
                    : "No matching documents."}
                </CommandEmpty>
                <CommandGroup>
                  {available.map((doc) => (
                    <CommandItem
                      key={doc.doc_id}
                      value={doc.filename}
                      onSelect={() => {
                        onSelect(doc);
                        setOpen(false);
                      }}
                    >
                      <FileTextIcon className="size-4 text-muted-foreground" />
                      <span className="truncate">{doc.filename}</span>
                    </CommandItem>
                  ))}
                </CommandGroup>
              </>
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
