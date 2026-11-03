from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_current_user, require_document_access, CurrentUser
from src.storage.database import get_graph_data, get_node, list_documents
from src.security import generate_source_token

router = APIRouter()


@router.get("/graph")
def graph_endpoint(doc_id: str = None, user: CurrentUser = Depends(get_current_user)):
    """Returns entity co-occurrence graph data for visualization.
    Pass ?doc_id=... to scope to one document, omit for the full graph
    (scoped to the caller's own + shared documents, never another user's)."""
    if doc_id:
        require_document_access(doc_id, user)
        return get_graph_data(doc_id)

    allowed_doc_ids = [d["doc_id"] for d in list_documents(user_id=user.id)]
    return get_graph_data(allowed_doc_ids=allowed_doc_ids)


@router.get("/graph/section/{node_id}")
def graph_section_endpoint(node_id: str, user: CurrentUser = Depends(get_current_user)):
    """Returns the source section behind a graph node, for the UI's
    click-to-inspect panel. Also issues a signed source_token (see
    src/security.py) so the "open source document" link can be built
    without the frontend needing to mint one itself."""
    node = get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"Section '{node_id}' not found.")

    document = require_document_access(node["doc_id"], user)

    return {
        "doc_id": node["doc_id"],
        "heading_path": node.get("heading_path"),
        "content": node.get("content"),
        "page": node.get("page"),
        "source_token": generate_source_token(document["filename"], user.id),
    }
