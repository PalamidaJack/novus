"""
Knowledge Base integration for NOVUS.

Enables RAG (Retrieval Augmented Generation) functionality with document
ingestion, chunking, embedding, and semantic search.
"""

from __future__ import annotations

import os
import asyncio
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import hashlib
import structlog

logger = structlog.get_logger()

# Optional dependencies
try:
    from langchain.text_splitter import RecursiveCharacterTextSplitter
    from langchain_community.document_loaders import (
        PyPDFLoader, TextLoader, CSVLoader, 
        DocxLoader, UnstructuredURLLoader
    )
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False


@dataclass
class Document:
    """A document in the knowledge base."""
    id: str
    content: str
    metadata: Dict[str, Any]
    embedding: Optional[List[float]] = None
    chunk_ids: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class SearchResult:
    """A search result from the knowledge base."""
    document: Document
    score: float
    chunk: str
    metadata: Dict[str, Any]


class KnowledgeBase:
    """
    Knowledge base for RAG (Retrieval Augmented Generation).
    
    Features:
    - Document ingestion (PDF, text, CSV, DOCX, URLs)
    - Text chunking with overlap
    - Embedding generation
    - Semantic search
    - Source citation
    """
    
    def __init__(
        self,
        name: str = "default",
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        embedding_model: str = "default"
    ):
        self.name = name
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.embedding_model = embedding_model
        
        self.documents: Dict[str, Document] = {}
        self.chunks: Dict[str, str] = {}  # chunk_id -> content
        self.chunk_embeddings: Dict[str, List[float]] = {}
        
        # Text splitter
        self._splitter = None
        if LANGCHAIN_AVAILABLE:
            self._splitter = RecursiveCharacterTextSplitter(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                separators=["\n\n", "\n", " ", ""]
            )
        
        logger.info("knowledge_base_initialized", name=name)
    
    async def add_document(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        source: Optional[str] = None
    ) -> str:
        """
        Add a document to the knowledge base.
        
        Args:
            content: Document text content
            metadata: Optional metadata
            source: Source identifier
        
        Returns:
            Document ID
        """
        # Generate ID
        doc_id = hashlib.md5(
            (content + str(datetime.utcnow())).encode()
        ).hexdigest()[:16]
        
        metadata = metadata or {}
        metadata["source"] = source
        
        # Create document
        document = Document(
            id=doc_id,
            content=content,
            metadata=metadata
        )
        
        # Chunk the document
        chunks = await self._chunk_document(content, doc_id)
        document.chunk_ids = list(chunks.keys())
        
        # Generate embeddings
        await self._embed_chunks(chunks, doc_id)
        
        # Store
        self.documents[doc_id] = document
        self.chunks.update(chunks)
        
        logger.info(
            "document_added",
            doc_id=doc_id,
            chunks=len(chunks),
            source=source
        )
        
        return doc_id
    
    async def add_file(
        self,
        file_path: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Load a file into the knowledge base."""
        if not LANGCHAIN_AVAILABLE:
            raise RuntimeError("LangChain not installed. Install with: pip install langchain")
        
        path = Path(file_path)
        content = ""
        
        if path.suffix == ".pdf":
            loader = PyPDFLoader(str(path))
            pages = await loader.alazy_load()
            content = "\n\n".join([p.page_content for p in pages])
        elif path.suffix == ".txt":
            loader = TextLoader(str(path))
            docs = await loader.alazy_load()
            content = "\n\n".join([d.page_content for d in docs])
        elif path.suffix == ".csv":
            loader = CSVLoader(str(path))
            docs = await loader.alazy_load()
            content = "\n\n".join([d.page_content for d in docs])
        elif path.suffix in [".doc", ".docx"]:
            loader = DocxLoader(str(path))
            docs = await loader.alazy_load()
            content = "\n\n".join([d.page_content for d in docs])
        else:
            raise ValueError(f"Unsupported file type: {path.suffix}")
        
        return await self.add_document(
            content=content,
            metadata=metadata,
            source=str(path)
        )
    
    async def add_url(
        self,
        url: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Load content from a URL."""
        if not LANGCHAIN_AVAILABLE:
            raise RuntimeError("LangChain not installed")
        
        loader = UnstructuredURLLoader(urls=[url])
        docs = await loader.alazy_load()
        content = "\n\n".join([d.page_content for d in docs])
        
        return await self.add_document(
            content=content,
            metadata=metadata,
            source=url
        )
    
    async def search(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.0
    ) -> List[SearchResult]:
        """
        Semantic search over the knowledge base.
        
        Args:
            query: Search query
            top_k: Number of results to return
            min_score: Minimum relevance score
        
        Returns:
            List of search results
        """
        # Generate query embedding
        query_embedding = await self._generate_embedding(query)
        
        # Calculate similarities
        results = []
        for chunk_id, chunk_embedding in self.chunk_embeddings.items():
            if chunk_embedding is None:
                continue
            
            score = self._cosine_similarity(query_embedding, chunk_embedding)
            
            if score >= min_score:
                # Find document
                doc = None
                for d in self.documents.values():
                    if chunk_id in d.chunk_ids:
                        doc = d
                        break
                
                if doc:
                    results.append(SearchResult(
                        document=doc,
                        score=score,
                        chunk=self.chunks.get(chunk_id, ""),
                        metadata=doc.metadata
                    ))
        
        # Sort by score and return top_k
        results.sort(key=lambda r: r.score, reverse=True)
        
        return results[:top_k]
    
    async def get_context(
        self,
        query: str,
        max_tokens: int = 4000
    ) -> str:
        """
        Get relevant context for a query.
        
        Includes source citations.
        """
        results = await self.search(query, top_k=10)
        
        context_parts = []
        total_chars = 0
        
        for result in results:
            chunk = result.chunk[:500]  # Limit chunk size
            source = result.metadata.get("source", "Unknown")
            
            context_part = f"[Source: {source}, Relevance: {result.score:.2f}]\n{chunk}\n"
            
            if total_chars + len(context_part) > max_tokens * 4:  # Rough token estimate
                break
            
            context_parts.append(context_part)
            total_chars += len(context_part)
        
        return "\n---\n\n".join(context_parts)
    
    async def _chunk_document(
        self,
        content: str,
        doc_id: str
    ) -> Dict[str, str]:
        """Split document into chunks."""
        if self._splitter:
            texts = self._splitter.split_text(content)
        else:
            # Simple fallback chunking
            texts = [
                content[i:i+self.chunk_size]
                for i in range(0, len(content), self.chunk_size - self.chunk_overlap)
            ]
        
        chunks = {}
        for i, text in enumerate(texts):
            chunk_id = f"{doc_id}_chunk_{i}"
            chunks[chunk_id] = text
        
        return chunks
    
    async def _embed_chunks(
        self,
        chunks: Dict[str, str],
        doc_id: str
    ) -> None:
        """Generate embeddings for chunks."""
        for chunk_id, content in chunks.items():
            embedding = await self._generate_embedding(content)
            self.chunk_embeddings[chunk_id] = embedding
    
    async def _generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for text."""
        # Use a simple hash-based embedding as fallback
        # In production, use OpenAI, Cohere, or local embeddings
        
        if not NUMPY_AVAILABLE:
            # Return simple hash
            hash_val = int(hashlib.md5(text.encode()).hexdigest(), 16)
            return [(hash_val % 1000) / 1000.0 for _ in range(512)]
        
        # Simple TF-IDF-like embedding (for demo)
        words = text.lower().split()
        embedding = [0.0] * 512
        
        for i, word in enumerate(words[:512]):
            hash_val = hash(word) % 512
            embedding[hash_val] += 1.0
        
        # Normalize
        norm = sum(x*x for x in embedding) ** 0.5
        if norm > 0:
            embedding = [x/norm for x in embedding]
        
        return embedding
    
    def _cosine_similarity(
        self,
        a: List[float],
        b: List[float]
    ) -> float:
        """Calculate cosine similarity."""
        if not NUMPY_AVAILABLE:
            # Simple implementation
            dot = sum(x*y for x, y in zip(a, b))
            mag_a = sum(x*x for x in a) ** 0.5
            mag_b = sum(x*x for x in b) ** 0.5
            return dot / (mag_a * mag_b) if mag_a * mag_b > 0 else 0.0
        
        a_vec = np.array(a)
        b_vec = np.array(b)
        return float(np.dot(a_vec, b_vec) / (np.linalg.norm(a_vec) * np.linalg.norm(b_vec)))
    
    def get_stats(self) -> Dict[str, Any]:
        """Get knowledge base statistics."""
        return {
            "name": self.name,
            "total_documents": len(self.documents),
            "total_chunks": len(self.chunks),
            "total_size_chars": sum(len(d.content) for d in self.documents.values()),
        }


class KnowledgeBaseManager:
    """
    Manages multiple knowledge bases.
    """
    
    def __init__(self):
        self.bases: Dict[str, KnowledgeBase] = {}
    
    def create_base(
        self,
        name: str,
        **kwargs
    ) -> KnowledgeBase:
        """Create a new knowledge base."""
        base = KnowledgeBase(name=name, **kwargs)
        self.bases[name] = base
        return base
    
    def get_base(self, name: str) -> Optional[KnowledgeBase]:
        """Get a knowledge base by name."""
        return self.bases.get(name)
    
    def list_bases(self) -> List[str]:
        """List all knowledge base names."""
        return list(self.bases.keys())


# Global manager
_kb_manager = KnowledgeBaseManager()


def get_knowledge_base(name: str = "default") -> KnowledgeBase:
    """Get or create a knowledge base."""
    if name not in _kb_manager.bases:
        _kb_manager.bases[name] = KnowledgeBase(name=name)
    return _kb_manager.bases[name]
