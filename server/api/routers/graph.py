from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_current_user, CurrentUser
from src.storage.database import get_graph_data, get_node

router = APIRouter()


@router.get("/graph")
async def graph_endpoint(doc_id: str = None, user: CurrentUser = Depends(get_current_user)):
    """Returns entity co-occurrence graph data for visualization.
    Pass ?doc_id=... to scope to one document, omit for the full graph."""
    return get_graph_data(doc_id)


@router.get("/graph/section/{node_id}")
async def graph_section_endpoint(node_id: str, user: CurrentUser = Depends(get_current_user)):
    """Returns the source section behind a graph node, for the UI's
    click-to-inspect panel. The frontend already has the doc_id -> filename
    mapping from /documents, so this only needs to return the node itself."""
    node = get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"Section '{node_id}' not found.")
    return {
        "doc_id": node["doc_id"],
        "heading_path": node.get("heading_path"),
        "content": node.get("content"),
        "page": node.get("page"),
    }
