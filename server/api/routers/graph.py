from typing import Optional

from fastapi import APIRouter, Depends

from api.deps import get_current_user, CurrentUser
from api.services.graph_service import GraphService

router = APIRouter()


@router.get("/graph")
def graph_endpoint(doc_id: Optional[str] = None, user: CurrentUser = Depends(get_current_user)):
    return GraphService.get_graph(doc_id, user)


@router.get("/graph/section/{node_id}")
def graph_section_endpoint(node_id: str, user: CurrentUser = Depends(get_current_user)):
    return GraphService.get_section(node_id, user)
