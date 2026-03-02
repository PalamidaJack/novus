"""
Unified Memory System for NOVUS.

Implements three-form memory (token, parametric, latent) with generative
memory capabilities inspired by recent research.
"""

from __future__ import annotations

import json
import hashlib
from typing import Dict, List, Optional, Any, Set
from datetime import datetime, timedelta
from dataclasses import dataclass
import structlog
import numpy as np

from novus.core.models import MemoryEntry, MemoryType, Task

logger = structlog.get_logger()


@dataclass
class MemoryRetrieval:
    """Result of a memory retrieval operation."""
    entry: MemoryEntry
    relevance_score: float
    retrieval_method: str


class UnifiedMemory:
    """
    Unified memory system implementing three-form memory architecture.
    
    Three forms:
    1. Token-level: Explicit, human-readable (episodic, semantic, procedural)
    2. Parametric: Learned, implicit (model weights, adapters)
    3. Latent: Compressed, dense (embeddings, KV cache)
    
    Plus generative memory: synthesizing relevant knowledge on demand.
    """
    
    def __init__(self, max_entries: int = 10000):
        self.max_entries = max_entries
        
        # Token-level memory stores
        self.episodic: Dict[str, MemoryEntry] = {}
        self.semantic: Dict[str, MemoryEntry] = {}
        self.procedural: Dict[str, MemoryEntry] = {}
        
        # Latent memory
        self.embeddings: Dict[str, List[float]] = {}
        self.embedding_dim = 1536  # OpenAI ada-002 dimension
        
        # Generative memory cache
        self._generative_cache: Dict[str, str] = {}
        self._cache_ttl = timedelta(hours=1)
        
        # Indices
        self._tag_index: Dict[str, Set[str]] = {}
        self._task_index: Dict[str, Set[str]] = {}
        
        logger.info("unified_memory_initialized", max_entries=max_entries)
    
    async def store(
        self,
        content: str,
        memory_type: MemoryType,
        metadata: Optional[Dict[str, Any]] = None,
        embedding: Optional[List[float]] = None,
        task_id: Optional[str] = None
    ) -> MemoryEntry:
        """
        Store a new memory entry.
        
        Args:
            content: The memory content
            memory_type: Type of memory
            metadata: Optional metadata
            embedding: Optional pre-computed embedding
            task_id: Optional associated task
        """
        entry = MemoryEntry(
            memory_type=memory_type,
            content=content,
            embedding=embedding,
            metadata=metadata or {},
            source_task_id=task_id
        )
        
        # Store in appropriate bucket
        store = self._get_store(memory_type)
        store[entry.id] = entry
        
        # Generate embedding if not provided
        if not embedding:
            entry.embedding = await self._generate_embedding(content)
        
        self.embeddings[entry.id] = entry.embedding
        
        # Update indices
        if metadata:
            for tag in metadata.get("tags", []):
                if tag not in self._tag_index:
                    self._tag_index[tag] = set()
                self._tag_index[tag].add(entry.id)
        
        if task_id:
            if task_id not in self._task_index:
                self._task_index[task_id] = set()
            self._task_index[task_id].add(entry.id)
        
        # Evict if over capacity
        await self._maybe_evict()
        
        logger.debug("memory_stored", entry_id=entry.id, type=memory_type.value)
        return entry
    
    async def store_experience(
        self,
        task: Task,
        outcome: str,
        lessons_learned: Optional[str] = None
    ) -> MemoryEntry:
        """
        Store an experience from task execution.
        
        This creates an episodic memory with context about what happened.
        """
        content = f"""Task: {task.description}
Outcome: {outcome}
Result: {task.result}
"""
        if lessons_learned:
            content += f"\nLessons: {lessons_learned}"
        
        return await self.store(
            content=content,
            memory_type=MemoryType.EPISODIC,
            metadata={
                "task_id": task.id,
                "outcome": outcome,
                "duration": task.metrics.get("duration_seconds"),
            },
            task_id=task.id
        )
    
    async def retrieve(
        self,
        query: str,
        memory_types: Optional[List[MemoryType]] = None,
        k: int = 5,
        threshold: float = 0.7
    ) -> List[MemoryRetrieval]:
        """
        Retrieve relevant memories using multiple strategies.
        
        Strategies:
        1. Exact match (tag-based)
        2. Semantic similarity (embedding-based)
        3. Temporal recency
        4. Generative synthesis (if retrieval insufficient)
        """
        results: List[MemoryRetrieval] = []
        
        # Determine which stores to search
        types_to_search = memory_types or list(MemoryType)
        
        # Strategy 1: Tag-based exact match
        tag_results = await self._retrieve_by_tags(query)
        results.extend(tag_results)
        
        # Strategy 2: Semantic similarity
        semantic_results = await self._retrieve_by_similarity(query, types_to_search, k)
        results.extend(semantic_results)
        
        # Strategy 3: Temporal (recent memories)
        recent_results = await self._retrieve_recent(types_to_search, k)
        results.extend(recent_results)
        
        # Deduplicate and rank
        seen_ids: Set[str] = set()
        unique_results = []
        for r in results:
            if r.entry.id not in seen_ids:
                seen_ids.add(r.entry.id)
                unique_results.append(r)
        
        # Sort by relevance
        unique_results.sort(key=lambda x: x.relevance_score, reverse=True)
        
        # Strategy 4: Generative synthesis if insufficient
        if len(unique_results) < k or unique_results[0].relevance_score < threshold:
            generated = await self._generate_relevant_knowledge(query)
            if generated:
                gen_entry = MemoryEntry(
                    memory_type=MemoryType.GENERATIVE,
                    content=generated,
                    metadata={"generated_for": query}
                )
                unique_results.append(MemoryRetrieval(
                    entry=gen_entry,
                    relevance_score=0.6,  # Lower confidence for generated
                    retrieval_method="generative"
                ))
        
        return unique_results[:k]
    
    async def retrieve_relevant(self, query: str, k: int = 5) -> List[str]:
        """Simple interface returning just content strings."""
        retrievals = await self.retrieve(query, k=k)
        return [r.entry.content for r in retrievals]
    
    async def _retrieve_by_tags(self, query: str) -> List[MemoryRetrieval]:
        """Retrieve memories matching tags in query."""
        results = []
        
        # Extract tags from query (simplified)
        query_tags = set(query.lower().split())
        
        for tag, entry_ids in self._tag_index.items():
            if tag.lower() in query_tags:
                for entry_id in entry_ids:
                    entry = self._find_entry(entry_id)
                    if entry:
                        results.append(MemoryRetrieval(
                            entry=entry,
                            relevance_score=0.9,  # High for tag match
                            retrieval_method="tag"
                        ))
        
        return results
    
    async def _retrieve_by_similarity(
        self,
        query: str,
        memory_types: List[MemoryType],
        k: int
    ) -> List[MemoryRetrieval]:
        """Retrieve memories by embedding similarity."""
        if not self.embeddings:
            return []
        
        # Generate query embedding
        query_embedding = await self._generate_embedding(query)
        
        # Calculate similarities
        similarities = []
        for entry_id, embedding in self.embeddings.items():
            entry = self._find_entry(entry_id)
            if not entry or entry.memory_type not in memory_types:
                continue
            
            sim = self._cosine_similarity(query_embedding, embedding)
            similarities.append((entry, sim))
        
        # Return top-k
        similarities.sort(key=lambda x: x[1], reverse=True)
        return [
            MemoryRetrieval(
                entry=entry,
                relevance_score=sim,
                retrieval_method="semantic"
            )
            for entry, sim in similarities[:k]
        ]
    
    async def _retrieve_recent(
        self,
        memory_types: List[MemoryType],
        k: int
    ) -> List[MemoryRetrieval]:
        """Retrieve recent memories."""
        all_entries = []
        for mem_type in memory_types:
            store = self._get_store(mem_type)
            all_entries.extend(store.values())
        
        # Sort by recency
        all_entries.sort(key=lambda e: e.last_accessed, reverse=True)
        
        return [
            MemoryRetrieval(
                entry=entry,
                relevance_score=0.5,  # Neutral for recency
                retrieval_method="temporal"
            )
            for entry in all_entries[:k]
        ]
    
    async def _generate_relevant_knowledge(self, query: str) -> Optional[str]:
        """
        Generate relevant knowledge when retrieval is insufficient.
        
        This implements "generative memory" - synthesizing what WOULD be
        relevant to know rather than just retrieving existing memories.
        """
        # Check cache
        cache_key = hashlib.md5(query.encode()).hexdigest()
        if cache_key in self._generative_cache:
            return self._generative_cache[cache_key]
        
        # Retrieve some context to ground generation
        context = await self._retrieve_by_similarity(query, list(MemoryType), k=3)
        context_str = "\n".join([r.entry.content for r in context])
        
        # Generate synthesized knowledge
        # In production, this would call an LLM
        synthesized = self._synthesize_knowledge(query, context_str)
        
        # Cache result
        self._generative_cache[cache_key] = synthesized
        
        logger.debug("knowledge_synthesized", query=query[:50])
        return synthesized
    
    def _synthesize_knowledge(self, query: str, context: str) -> str:
        """Synthesize relevant knowledge (placeholder for LLM call)."""
        return f"[Synthesized knowledge for: {query[:50]}... based on {len(context)} chars of context]"
    
    def _find_entry(self, entry_id: str) -> Optional[MemoryEntry]:
        """Find an entry across all memory stores."""
        for store in [self.episodic, self.semantic, self.procedural]:
            if entry_id in store:
                entry = store[entry_id]
                entry.touch()
                return entry
        return None
    
    def _get_store(self, memory_type: MemoryType) -> Dict[str, MemoryEntry]:
        """Get the appropriate store for a memory type."""
        if memory_type == MemoryType.EPISODIC:
            return self.episodic
        elif memory_type == MemoryType.SEMANTIC:
            return self.semantic
        elif memory_type == MemoryType.PROCEDURAL:
            return self.procedural
        else:
            return self.semantic  # Default
    
    async def _generate_embedding(self, content: str) -> List[float]:
        """
        Generate embedding for content.
        
        In production, this would call an embedding API.
        For now, return a random embedding (placeholder).
        """
        # Deterministic random based on content hash for testing
        hash_val = int(hashlib.md5(content.encode()).hexdigest(), 16)
        rng = np.random.RandomState(hash_val % (2**32 - 1))
        return rng.randn(self.embedding_dim).tolist()
    
    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        a_vec = np.array(a)
        b_vec = np.array(b)
        return float(np.dot(a_vec, b_vec) / (np.linalg.norm(a_vec) * np.linalg.norm(b_vec)))
    
    async def _maybe_evict(self) -> None:
        """Evict old memories if over capacity."""
        total = len(self.episodic) + len(self.semantic) + len(self.procedural)
        
        if total <= self.max_entries:
            return
        
        # Evict least recently used from each store
        to_evict = total - self.max_entries
        
        for store in [self.episodic, self.semantic, self.procedural]:
            if to_evict <= 0:
                break
            
            # Sort by last accessed
            sorted_entries = sorted(
                store.items(),
                key=lambda x: x[1].last_accessed
            )
            
            for entry_id, entry in sorted_entries[:to_evict]:
                del store[entry_id]
                if entry_id in self.embeddings:
                    del self.embeddings[entry_id]
                to_evict -= 1
                
                logger.debug("memory_evicted", entry_id=entry_id)
    
    async def consolidate(self) -> None:
        """
        Memory consolidation - organize and optimize memories.
        
        This would be called periodically (like during "sleep" phases).
        """
        logger.info("memory_consolidation_started")
        
        # 1. Extract generalizations from episodic memories
        await self._extract_generalizations()
        
        # 2. Merge duplicate memories
        await self._deduplicate()
        
        # 3. Build associations between related memories
        await self._build_associations()
        
        logger.info("memory_consolidation_completed")
    
    async def _extract_generalizations(self) -> None:
        """Extract general patterns from episodic memories."""
        # Group by outcome
        by_outcome: Dict[str, List[MemoryEntry]] = {}
        for entry in self.episodic.values():
            outcome = entry.metadata.get("outcome", "unknown")
            if outcome not in by_outcome:
                by_outcome[outcome] = []
            by_outcome[outcome].append(entry)
        
        # Create semantic memories for patterns
        for outcome, entries in by_outcome.items():
            if len(entries) >= 3:  # Need multiple examples
                pattern = f"Pattern: Tasks with outcome '{outcome}'"
                await self.store(
                    content=pattern,
                    memory_type=MemoryType.SEMANTIC,
                    metadata={"derived_from": [e.id for e in entries]}
                )
    
    async def _deduplicate(self) -> None:
        """Merge or remove duplicate memories."""
        # Find near-duplicate embeddings
        to_remove = []
        entry_ids = list(self.embeddings.keys())
        
        for i, id1 in enumerate(entry_ids):
            for id2 in entry_ids[i+1:]:
                sim = self._cosine_similarity(
                    self.embeddings[id1],
                    self.embeddings[id2]
                )
                if sim > 0.95:  # Very similar
                    # Keep newer one
                    to_remove.append(min(id1, id2, key=lambda x: self._find_entry(x).created_at.timestamp() if self._find_entry(x) else 0))
        
        for entry_id in set(to_remove):
            entry = self._find_entry(entry_id)
            if entry:
                store = self._get_store(entry.memory_type)
                del store[entry_id]
                del self.embeddings[entry_id]
    
    async def _build_associations(self) -> None:
        """Build associations between related memories."""
        # Find memories with high similarity
        for id1, emb1 in self.embeddings.items():
            entry1 = self._find_entry(id1)
            if not entry1:
                continue
            
            for id2, emb2 in self.embeddings.items():
                if id1 >= id2:
                    continue
                
                sim = self._cosine_similarity(emb1, emb2)
                if sim > 0.8:  # Related
                    entry2 = self._find_entry(id2)
                    if entry2 and id2 not in entry1.related_entries:
                        entry1.related_entries.append(id2)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics."""
        return {
            "total_entries": len(self.episodic) + len(self.semantic) + len(self.procedural),
            "episodic": len(self.episodic),
            "semantic": len(self.semantic),
            "procedural": len(self.procedural),
            "embeddings": len(self.embeddings),
            "tags": len(self._tag_index),
        }
