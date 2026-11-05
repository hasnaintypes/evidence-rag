from typing import Any, Dict, Optional

from fastapi import HTTPException

from api.authz import get_owned_document, get_owned_graph_scope
from api.deps import CurrentUser
from src.security import generate_source_token
from src.storage.database import get_graph_data, get_node


class GraphService:
    """
    Owns entity-graph reads and section inspection - loading the
    resource, asserting ownership via api/authz.py, then acting - so
    api/routers/graph.py stays a thin HTTP-shape adapter. See GitHub
    issue #18 / 02-Architecture.md's Proposed Changes.
    """

    @staticmethod
    def get_graph(doc_id: Optional[str], user: CurrentUser) -> Dict[str, Any]:
        """Entity co-occurrence graph data for visualization. `doc_id`
        scopes to one document; omit for the full graph (scoped to the
        caller's own + shared documents, never another user's)."""
        scope = get_owned_graph_scope(doc_id, user)
        return get_graph_data(**scope)

    @staticmethod
    def get_section(node_id: str, user: CurrentUser) -> Dict[str, Any]:
        """The source section behind a graph node, for the UI's
        click-to-inspect panel. Also issues a signed source_token (see
        src/security.py) so the "open source document" link can be built
        without the frontend needing to mint one itself."""
        node = get_node(node_id)
        if not node:
            raise HTTPException(status_code=404, detail=f"Section '{node_id}' not found.")

        document = get_owned_document(node["doc_id"], user)

        return {
            "doc_id": node["doc_id"],
            "heading_path": node.get("heading_path"),
            "content": node.get("content"),
            "page": node.get("page"),
            "source_token": generate_source_token(document["filename"], user.id),
        }
