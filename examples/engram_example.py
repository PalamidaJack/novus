#!/usr/bin/env python3
"""
Example: Engram Memory System

Demonstrates the O(1) conditional memory architecture.
"""

import numpy as np
from novus.memory.engram import (
    EngramModule, EngramMemoryTable, NGramKey,
    ContextAwareGating, TokenizerCompressor
)


def engram_example():
    """Engram memory example."""
    print("=" * 60)
    print("NOVUS Engram Memory Example")
    print("=" * 60)
    
    # Example 1: Tokenizer Compression
    print("\n--- Example 1: Tokenizer Compression ---")
    
    compressor = TokenizerCompressor(vocab_size=128000)
    
    # Simulate tokens
    tokens = [
        (100, "Hello"),
        (101, "hello"),
        (102, "HELLO"),
        (103, "World"),
        (104, "world"),
    ]
    
    print("Token compression:")
    for token_id, text in tokens:
        compressed = compressor.compress(token_id, text)
        print(f"  '{text}' (ID: {token_id}) -> Compressed ID: {compressed}")
    
    print(f"\nCompression ratio: {compressor.compressed_vocab_size}/{len(tokens)} unique")
    
    # Example 2: Engram Memory Table
    print("\n--- Example 2: O(1) Memory Lookup ---")
    
    table = EngramMemoryTable(
        embedding_dim=128,
        max_ngram_order=3,
        num_hash_heads=2,
        table_size=1_000_000
    )
    
    # Create n-gram keys
    ngrams = [
        NGramKey(tokens=(100, 200), order=2),
        NGramKey(tokens=(200, 300, 400), order=3),
        NGramKey(tokens=(100, 200), order=2),  # Duplicate
    ]
    
    # Insert embeddings
    print("Inserting memories...")
    for i, ngram in enumerate(ngrams):
        embedding = np.random.randn(128 // 2)  # Per-head dimension
        table.insert(ngram, embedding, head_id=0)
        print(f"  Inserted n-gram {i}: {ngram.tokens}")
    
    # Look up memories
    print("\nLooking up memories...")
    for i, ngram in enumerate(ngrams):
        result = table.lookup(ngram)
        status = "HIT" if result is not None else "MISS"
        print(f"  Lookup {i}: {status} (tokens: {ngram.tokens})")
    
    stats = table.get_stats()
    print(f"\nMemory table stats:")
    for key, value in stats.items():
        print(f"  {key}: {value:.4f}" if isinstance(value, float) else f"  {key}: {value}")
    
    # Example 3: Context-Aware Gating
    print("\n--- Example 3: Context-Aware Gating ---")
    
    gating = ContextAwareGating(dim=512)
    
    context = np.random.randn(512)
    memory = np.random.randn(512)
    
    gate_value = gating.compute_gate(context, memory)
    gated_memory, gate = gating.apply(context, memory)
    
    print(f"Gate value: {gate:.4f}")
    print(f"Gate interpretation: {'Highly relevant' if gate > 0.7 else 'Somewhat relevant' if gate > 0.3 else 'Not relevant'}")
    print(f"Gated memory shape: {gated_memory.shape}")
    
    # Example 4: Full Engram Module
    print("\n--- Example 4: Full Engram Module ---")
    
    engram = EngramModule(
        embedding_dim=512,
        max_ngram_order=5,
        num_hash_heads=4,
        vocab_size=128000
    )
    
    # Simulate processing
    tokens = [100, 200, 300, 400, 500]
    context = np.random.randn(512)
    
    print(f"Input tokens: {tokens}")
    print(f"Context shape: {context.shape}")
    
    # Extract n-grams
    ngrams = engram.extract_ngrams(tokens)
    print(f"\nExtracted {len(ngrams)} n-grams:")
    for i, ngram in enumerate(ngrams[:5]):  # Show first 5
        print(f"  {i+1}. Order {ngram.order}: {ngram.tokens}")
    if len(ngrams) > 5:
        print(f"  ... and {len(ngrams) - 5} more")
    
    # Process through Engram
    output, gate_values = engram.forward(tokens, context, return_gate_values=True)
    
    print(f"\nEngram output shape: {output.shape}")
    if gate_values:
        print(f"Number of memories used: {len(gate_values)}")
        print(f"Average gate value: {np.mean(gate_values):.4f}")
    
    # Show module stats
    stats = engram.get_stats()
    print(f"\nModule statistics:")
    for key, value in stats.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.4f}")
        else:
            print(f"  {key}: {value}")
    
    # Example 5: Memory Consolidation
    print("\n--- Example 5: Memory Consolidation ---")
    
    # Simulate learning from multiple lookups
    for _ in range(10):
        tokens = [100, 200, 300]
        context = np.random.randn(512)
        output, _ = engram.forward(tokens, context, return_gate_values=True)
        engram.lookup_history.append((tokens, output))
    
    print(f"Lookup history size: {len(engram.lookup_history)}")
    print("Consolidating frequently accessed patterns...")
    
    engram.consolidate_memories()
    
    print("Memory consolidation complete!")
    
    print("\n" + "=" * 60)
    print("Example completed!")
    print("=" * 60)


if __name__ == "__main__":
    engram_example()
