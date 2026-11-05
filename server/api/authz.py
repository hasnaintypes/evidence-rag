from typing import Any, Dict, Optional

from fastapi import HTTPException

from api.deps import CurrentUser
from src.storage.database import get_conversation, get_document_record, list_documents

# --------------------------------------------------------------------------- #
# Shared ownership-check helpers
#
# Every resource-scoped route needs the same shape of check: load the
# resource, confirm the caller can access it, 404 (not 403) otherwise so a
# non-owner can't even confirm a given ID exists. That pattern was proven
# correct in api/routers/conversations.py's original _get_owned_conversation
# and api/deps.py's original require_document_access, each hand-rolled
# separately per router - this module centralizes them (plus a new
# graph-specific helper) so every service in api/services/ shares one
# implementation instead of each author re-deriving the same check. See
# 02-Architecture.md's Proposed Changes and GitHub issue #18.
# --------------------------------------------------------------------------- #


def get_owned_document(doc_id: str, user: CurrentUser) -> Dict[str, Any]:
    """
    Raises 404 (not 403) for a doc_id that doesn't exist or belongs to
    someone else - doesn't confirm to a caller that a given ID exists at
    all. A None user_id on the document record means shared/demo (e.g.
    docs/fixtures/sample_docs), accessible to every signed-in user.

    Returns the {"user_id", "filename"} record so a caller that also
    needs the filename (e.g. GraphService.get_section()) doesn't have to
    re-fetch the same row a second time.
    """
    record = get_document_record(doc_id)
    if not record or (record["user_id"] is not None and record["user_id"] != user.id):
        raise HTTPException(status_code=404, detail="Document not found.")
    return record


def get_owned_document_for_mutation(doc_id: str, user: CurrentUser) -> Dict[str, Any]:
    """
    Stricter than get_owned_document() above: a shared/demo document
    (user_id IS NULL) is readable by every signed-in user but not safe for
    any one of them to rename/delete/re-ingest, since it has no single
    owner to attribute the mutation to and every other user still relies
    on it. Raises 404 for the same not-found-or-someone-else's cases as
    get_owned_document(), and 403 (not 404 - the resource's existence
    and shared status aren't secrets) when it exists but is shared.
    """
    record = get_owned_document(doc_id, user)
    if record["user_id"] is None:
        raise HTTPException(status_code=403, detail="Shared documents can't be modified.")
    return record


def get_owned_conversation(conversation_id: str, user: CurrentUser) -> Dict[str, Any]:
    """Raises 404 (not 403) for a conversation that exists but belongs to
    someone else - doesn't confirm to a caller that a given ID exists at all."""
    conversation = get_conversation(conversation_id)
    if not conversation or conversation["user_id"] != user.id:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return conversation


def get_owned_graph_scope(doc_id: Optional[str], user: CurrentUser) -> Dict[str, Any]:
    """
    Resolves the doc_id scope for GET /graph, mirroring
    src/storage/database.py's get_graph_data()'s two call shapes so
    GraphService can pass the result straight through as kwargs:
      - doc_id given: confirms the caller can access it (404s otherwise,
        via get_owned_document) and scopes to just that one document.
      - doc_id omitted: scopes to every document.doc_id the caller can
        access (their own uploads plus shared/demo documents) - never
        another user's private documents.
    """
    if doc_id:
        get_owned_document(doc_id, user)
        return {"doc_id": doc_id, "allowed_doc_ids": None}
    return {"doc_id": None, "allowed_doc_ids": [d["doc_id"] for d in list_documents(user_id=user.id)]}
