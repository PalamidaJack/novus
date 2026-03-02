"""
Engram-style Conditional Memory for NOVUS.

Implements DeepSeek's Engram architecture for O(1) knowledge lookups,
separating static memory from dynamic computation.
"""

from __future__ import annotations

import hashlib
import json
from typing import Dict, List, Optional, Tuple, Set, Any
from dataclasses import dataclass
import structlog
import numpy as np

logger = structlog.get_logger()


@dataclass
class NGramKey:
    """Represents an n-gram key for memory lookup."""
    tokens: Tuple[int, ...]
    order: int
    
    def hash(self, seed: int = 0) -> int:
        """Deterministic hash for this n-gram."""
        # Multiplicative-XOR hash as described in Engram paper
        h = seed
        for token in self.tokens:
            h = (h * 31) ^ token
        return abs(h)


class TokenizerCompressor:
    """
    Compresses tokenizer vocabulary by normalizing tokens.
    
    Reduces effective vocabulary size by ~23% through:
    - NFKC normalization
    - Lowercasing
    - Whitespace normalization
    """
    
    def __init__(self, vocab_size: int = 128000):
        self.vocab_size = vocab_size
        self._compression_map: Dict[int, int] = {}
        self._next_id = 0
    
    def compress(self, token_id: int, token_text: str) -> int:
        """
        Compress a token ID to canonical form.
        
        Args:
            token_id: Original token ID
            token_text: Token text for normalization
        
        Returns:
            Compressed canonical ID
        """
        if token_id in self._compression_map:
            return self._compression_map[token_id]
        
        # Normalize text
        normalized = self._normalize(token_text)
        
        # Create hash of normalized form
        norm_hash = hashlib.md5(normalized.encode()).hexdigest()[:16]
        
        # Map to new ID (with collision handling)
        if norm_hash not in self._compression_map:
            self._compression_map[norm_hash] = self._next_id
            self._compression_map[token_id] = self._next_id
            self._next_id += 1
        else:
            self._compression_map[token_id] = self._compression_map[norm_hash]
        
        return self._compression_map[token_id]
    
    def _normalize(self, text: str) -> str:
        """Normalize token text."""
        # Simplified normalization
        # In production would use NFKC Unicode normalization
        return text.lower().strip().replace(" ", "")
    
    @property
    def compressed_vocab_size(self) -> int:
        """Get size of compressed vocabulary."""
        return self._next_id


class EngramMemoryTable:
    """
    O(1) lookup memory table for static knowledge.
    
    This is the core of the Engram architecture - a massive embedding
    table that stores static n-gram patterns for instant retrieval.
    """
    
    def __init__(
        self,
        embedding_dim: int = 512,
        max_ngram_order: int = 5,
        num_hash_heads: int = 4,
        table_size: int = 100_000_000,  # 100M entries
    ):
        self.embedding_dim = embedding_dim
        self.max_ngram_order = max_ngram_order
        self.num_hash_heads = num_hash_heads
        self.table_size = table_size
        
        # Embedding tables per n-gram order and hash head
        # Using dictionaries for sparse storage (most entries empty)
        self.tables: Dict[int, Dict[int, np.ndarray]] = {
            (n, h): {}
            for n in range(2, max_ngram_order + 1)
            for h in range(num_hash_heads)
        }
        
        # Statistics
        self.access_count = 0
        self.hit_count = 0
        
        logger.info(
            "engram_memory_initialized",
            embedding_dim=embedding_dim,
            max_order=max_ngram_order,
            hash_heads=num_hash_heads,
            table_size=table_size
        )
    
    def lookup(
        self,
        ngram_key: NGramKey,
        return_all_heads: bool = True
    ) -> Optional[np.ndarray]:
        """
        O(1) lookup of n-gram embedding.
        
        Args:
            ngram_key: The n-gram to look up
            return_all_heads: Whether to concatenate all hash heads
        
        Returns:
            Embedding vector or None if not found
        """
        self.access_count += 1
        
        embeddings = []
        
        for head_id in range(self.num_hash_heads):
            # Compute hash for this head with different seed
            hash_val = ngram_key.hash(seed=head_id) % self.table_size
            
            # Look up in table
            table_key = (ngram_key.order, head_id)
            if table_key in self.tables:
                embedding = self.tables[table_key].get(hash_val)
                if embedding is not None:
                    embeddings.append(embedding)
        
        if embeddings:
            self.hit_count += 1
            if return_all_heads:
                return np.concatenate(embeddings)
            else:
                return embeddings[0]
        
        return None
    
    def insert(
        self,
        ngram_key: NGramKey,
        embedding: np.ndarray,
        head_id: int = 0
    ) -> None:
        """
        Insert an embedding into the memory table.
        
        Args:
            ngram_key: The n-gram key
            embedding: Embedding vector to store
            head_id: Which hash head to use
        """
        hash_val = ngram_key.hash(seed=head_id) % self.table_size
        table_key = (ngram_key.order, head_id)
        
        if table_key not in self.tables:
            self.tables[table_key] = {}
        
        self.tables[table_key][hash_val] = embedding
    
    def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics."""
        total_entries = sum(len(t) for t in self.tables.values())
        hit_rate = self.hit_count / max(1, self.access_count)
        
        return {
            "total_entries": total_entries,
            "access_count": self.access_count,
            "hit_count": self.hit_count,
            "hit_rate": hit_rate,
            "table_utilization": total_entries / (self.table_size * len(self.tables)),
        }


class ContextAwareGating:
    """
    Gating mechanism for conditioning Engram memory on current context.
    
    Implements the attention-based gating from the Engram paper:
    gate = sigmoid(RMSNorm(context)^T @ RMSNorm(memory_key) / sqrt(d))
    """
    
    def __init__(self, dim: int):
        self.dim = dim
        
        # Learnable projection matrices
        self.W_k = np.random.randn(dim, dim) * 0.02
        self.W_v = np.random.randn(dim, dim) * 0.02
    
    def rms_norm(self, x: np.ndarray) -> np.ndarray:
        """Root Mean Square normalization."""
        return x / np.sqrt(np.mean(x ** 2) + 1e-6)
    
    def compute_gate(
        self,
        context: np.ndarray,
        memory: np.ndarray
    ) -> float:
        """
        Compute gating value for memory given context.
        
        Returns a value between 0 and 1 indicating how relevant
        the memory is to the current context.
        """
        # Project memory
        k = self.W_k @ memory
        v = self.W_v @ memory
        
        # Normalize
        q_norm = self.rms_norm(context)
        k_norm = self.rms_norm(k)
        
        # Compute attention score
        score = np.dot(q_norm, k_norm) / np.sqrt(self.dim)
        
        # Sigmoid gate
        gate = 1 / (1 + np.exp(-score))
        
        return float(gate)
    
    def apply(
        self,
        context: np.ndarray,
        memory: np.ndarray
    ) -> Tuple[np.ndarray, float]:
        """
        Apply gated memory to context.
        
        Returns:
            (gated_memory, gate_value)
        """
        gate = self.compute_gate(context, memory)
        v = self.W_v @ memory
        gated = gate * v
        return gated, gate


class EngramModule:
    """
    Full Engram conditional memory module.
    
    Integrates:
    1. Tokenizer compression
    2. N-gram extraction
    3. O(1) memory lookup
    4. Context-aware gating
    """
    
    def __init__(
        self,
        embedding_dim: int = 512,
        max_ngram_order: int = 5,
        num_hash_heads: int = 4,
        vocab_size: int = 128000,
    ):
        self.embedding_dim = embedding_dim
        self.max_ngram_order = max_ngram_order
        
        # Components
        self.tokenizer_compressor = TokenizerCompressor(vocab_size)
        self.memory_table = EngramMemoryTable(
            embedding_dim=embedding_dim // num_hash_heads,
            max_ngram_order=max_ngram_order,
            num_hash_heads=num_hash_heads
        )
        self.gating = ContextAwareGating(embedding_dim)
        
        # Statistics
        self.total_lookups = 0
        self.cache_hits = 0
    
    def extract_ngrams(
        self,
        token_ids: List[int],
        compressed: bool = False
    ) -> List[NGramKey]:
        """
        Extract all n-grams from a sequence of tokens.
        
        Args:
            token_ids: List of token IDs
            compressed: Whether tokens are already compressed
        
        Returns:
            List of n-gram keys
        """
        ngrams = []
        
        for order in range(2, self.max_ngram_order + 1):
            for i in range(len(token_ids) - order + 1):
                ngram_tokens = tuple(token_ids[i:i+order])
                ngrams.append(NGramKey(tokens=ngram_tokens, order=order))
        
        return ngrams
    
    def forward(
        self,
        token_ids: List[int],
        context: np.ndarray,
        return_gate_values: bool = False
    ) -> Tuple[np.ndarray, Optional[List[float]]]:
        """
        Process tokens through Engram memory.
        
        Args:
            token_ids: Input token sequence
            context: Current hidden state context
            return_gate_values: Whether to return gating values
        
        Returns:
            (memory_output, gate_values)
        """
        self.total_lookups += 1
        
        # Extract n-grams
        ngrams = self.extract_ngrams(token_ids)
        
        # Look up memories
        memories = []
        gate_values = []
        
        for ngram in ngrams:
            mem = self.memory_table.lookup(ngram)
            if mem is not None:
                # Apply context-aware gating
                gated, gate = self.gating.apply(context, mem)
                memories.append(gated)
                gate_values.append(gate)
        
        if memories:
            self.cache_hits += 1
            # Aggregate memories (simple sum)
            output = np.sum(memories, axis=0)
        else:
            # No memories found - return zeros
            output = np.zeros(self.embedding_dim)
        
        if return_gate_values:
            return output, gate_values
        return output, None
    
    def memorize(
        self,
        token_ids: List[int],
        embedding: np.ndarray,
        importance: float = 1.0
    ) -> None:
        """
        Store a pattern in Engram memory.
        
        Args:
            token_ids: Token sequence to memorize
            embedding: Embedding to store
            importance: How important this memory is (affects storage)
        """
        ngrams = self.extract_ngrams(token_ids)
        
        # Split embedding across hash heads
        head_dim = self.embedding_dim // self.memory_table.num_hash_heads
        
        for head_id in range(self.memory_table.num_hash_heads):
            head_embedding = embedding[head_id*head_dim:(head_id+1)*head_dim]
            
            # Store for each n-gram
            for ngram in ngrams:
                self.memory_table.insert(ngram, head_embedding, head_id)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get module statistics."""
        table_stats = self.memory_table.get_stats()
        
        return {
            **table_stats,
            "total_module_lookups": self.total_lookups,
            "cache_hit_rate": self.cache_hits / max(1, self.total_lookups),
            "compressed_vocab_size": self.tokenizer_compressor.compressed_vocab_size,
        }


class EngramEnhancedAgent:
    """
    Agent enhanced with Engram-style conditional memory.
    
    This agent uses O(1) lookups for static knowledge, freeing up
    neural capacity for complex reasoning.
    """
    
    def __init__(self, agent_id: str, engram: Optional[EngramModule] = None):
        self.agent_id = agent_id
        self.engram = engram or EngramModule()
        
        # Track which tokens have been looked up
        self.lookup_history: List[Tuple[List[int], np.ndarray]] = []
    
    async def think(
        self,
        input_tokens: List[int],
        context: np.ndarray
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Process input with Engram-enhanced reasoning.
        
        The Engram handles static pattern recognition (O(1)),
        while the neural network handles dynamic reasoning.
        """
        # Query Engram for relevant memories
        engram_output, gate_values = self.engram.forward(
            input_tokens,
            context,
            return_gate_values=True
        )
        
        # Combine with context
        enhanced_context = context + engram_output
        
        # Store for learning
        self.lookup_history.append((input_tokens, engram_output))
        
        stats = {
            "engram_active": np.any(engram_output != 0),
            "avg_gate": np.mean(gate_values) if gate_values else 0.0,
            "num_memories_used": len(gate_values) if gate_values else 0,
        }
        
        return enhanced_context, stats
    
    def consolidate_memories(self) -> None:
        """
        Consolidate frequently accessed patterns into Engram memory.
        
        This implements the "learning" aspect - converting frequently
        used patterns into fast O(1) lookups.
        """
        # Count frequency of patterns
        pattern_counts: Dict[Tuple[int, ...], int] = {}
        
        for tokens, _ in self.lookup_history:
            ngrams = self.engram.extract_ngrams(tokens)
            for ngram in ngrams:
                key = ngram.tokens
                pattern_counts[key] = pattern_counts.get(key, 0) + 1
        
        # Store high-frequency patterns
        for (tokens, embedding), count in zip(self.lookup_history, 
                                              [pattern_counts.get(tuple(t), 0) 
                                               for t, _ in self.lookup_history]):
            if count > 5:  # Threshold for memorization
                self.engram.memorize(tokens, embedding, importance=count/100)
        
        # Clear history
        self.lookup_history.clear()


# Example usage
if __name__ == "__main__":
    # Create Engram module
    engram = EngramModule(
        embedding_dim=512,
        max_ngram_order=5,
        num_hash_heads=4
    )
    
    # Simulate token sequence
    tokens = [100, 200, 300, 400, 500]
    context = np.random.randn(512)
    
    # Process through Engram
    output, gate_values = engram.forward(tokens, context, return_gate_values=True)
    
    print(f"Engram output shape: {output.shape}")
    print(f"Stats: {engram.get_stats()}")
