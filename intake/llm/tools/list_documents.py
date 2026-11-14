"""Tool to list and enumerate documents in a loan application packet."""

from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field


class DocumentItem(BaseModel):
    """Basic document metadata item."""
    doc_id: str
    filename: str


class ListDocumentsInput(BaseModel):
    """Arguments for list_documents tool."""
    packet_id: Optional[str] = None
    documents: Optional[List[Dict[str, Any]]] = None
    packet: Optional[Dict[str, Any]] = None


class ListDocumentsOutput(BaseModel):
    """Result of list_documents tool."""
    packet_id: Optional[str] = None
    documents: List[DocumentItem] = Field(default_factory=list)
    count: int = 0


def list_documents(args: ListDocumentsInput) -> ListDocumentsOutput:
    """Enumerate documents available in the packet."""
    raw_docs = []
    packet_id = args.packet_id

    if args.packet:
        packet_id = args.packet.get("packet_id", packet_id)
        raw_docs = args.packet.get("documents", [])
    elif args.documents:
        raw_docs = args.documents

    items: List[DocumentItem] = []
    for d in raw_docs:
        doc_id = d.get("doc_id", "")
        filename = d.get("filename", "")
        if doc_id:
            items.append(DocumentItem(doc_id=doc_id, filename=filename))

    return ListDocumentsOutput(
        packet_id=packet_id,
        documents=items,
        count=len(items)
    )

