#!/usr/bin/env python3
"""
Optimize existing Qdrant collections for reduced RAM usage.

Applies scalar quantization and on-disk HNSW to existing collections
without requiring re-ingestion. Safe to run multiple times (idempotent).

Usage:
    python utility/optimize_qdrant_collections.py [--host localhost] [--port 6333]
"""

import argparse
import sys

from qdrant_client import QdrantClient, models


def optimize_collection(client: QdrantClient, name: str) -> None:
    """Apply optimizations to an existing collection."""
    info = client.get_collection(name)
    print(f"\n{'='*60}")
    print(f"Collection: {name}")
    print(f"  Points: {info.points_count}")
    print(f"  Vectors indexed: {info.indexed_vectors_count}")
    print(f"  Quantization: {info.config.quantization_config}")

    # 1. Enable scalar quantization (float32 → int8)
    if info.config.quantization_config is None:
        print(f"  → Enabling scalar quantization (INT8)...")
        client.update_collection(
            collection_name=name,
            quantization_config=models.ScalarQuantization(
                scalar=models.ScalarQuantizationConfig(
                    type=models.ScalarType.INT8,
                    quantile=0.99,
                    always_ram=True,
                ),
            ),
        )
        print(f"  ✓ Quantization enabled")
    else:
        print(f"  ✓ Quantization already active")

    # 2. Enable on-disk HNSW index
    hnsw = info.config.hnsw_config
    if not getattr(hnsw, "on_disk", False):
        print(f"  → Moving HNSW index to disk...")
        client.update_collection(
            collection_name=name,
            hnsw_config=models.HnswConfigDiff(on_disk=True),
        )
        print(f"  ✓ HNSW index set to on-disk")
    else:
        print(f"  ✓ HNSW index already on-disk")

    # 3. Enable on-disk vectors (memmap)
    vectors_config = info.config.params.vectors
    if not getattr(vectors_config, "on_disk", False):
        print(f"  → Moving vectors to on-disk (memmap)...")
        client.update_collection(
            collection_name=name,
            vectors_config=models.VectorParamsDiff(on_disk=True),
        )
        print(f"  ✓ Vectors set to on-disk (memmap)")
    else:
        print(f"  ✓ Vectors already on-disk")

    # Verify final state
    final = client.get_collection(name)
    print(f"\n  Final state:")
    print(f"    Quantization: {final.config.quantization_config}")
    print(f"    HNSW on-disk: {getattr(final.config.hnsw_config, 'on_disk', 'N/A')}")
    print(f"    Vectors on-disk: {getattr(final.config.params.vectors, 'on_disk', 'N/A')}")
    print(f"    Optimizer status: {final.optimizer_status}")


def main():
    parser = argparse.ArgumentParser(description="Optimize Qdrant collections for RAM efficiency")
    parser.add_argument("--host", default="localhost", help="Qdrant host (default: localhost)")
    parser.add_argument("--port", type=int, default=6333, help="Qdrant port (default: 6333)")
    args = parser.parse_args()

    print(f"Connecting to Qdrant at {args.host}:{args.port}...")
    client = QdrantClient(host=args.host, port=args.port, timeout=120.0)

    collections = client.get_collections().collections
    if not collections:
        print("No collections found.")
        return

    print(f"Found {len(collections)} collection(s): {[c.name for c in collections]}")

    for coll in collections:
        try:
            optimize_collection(client, coll.name)
        except Exception as e:
            print(f"  ✗ Error optimizing {coll.name}: {e}", file=sys.stderr)

    print(f"\n{'='*60}")
    print("Done! Optimizations applied. Qdrant will rebuild indexes in background.")
    print("Monitor progress via: curl http://localhost:6333/collections/tw_documents")


if __name__ == "__main__":
    main()
