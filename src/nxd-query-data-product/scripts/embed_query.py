"""Embed a query string with the same model the DP used to index its vectors.

For sentence-transformers IDs (`sentence-transformers/all-MiniLM-L6-v2`,
`all-mpnet-base-v2`, …) we run locally. For provider models (OpenAI, Cohere,
Voyage) the caller must pass an API key in the environment — those branches
are stubbed; extend per provider.

Writes the embedding as JSON {dim, vector} to stdout (or --out).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _local_sentence_transformer(model: str, query: str) -> list[float]:
    from sentence_transformers import SentenceTransformer  # type: ignore

    m = SentenceTransformer(model)
    return m.encode(query, normalize_embeddings=True).tolist()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True, help="Embedding model id (e.g. sentence-transformers/all-MiniLM-L6-v2)")
    p.add_argument("--query", required=True)
    p.add_argument("--out")
    args = p.parse_args()

    model_lc = args.model.lower()
    if "sentence-transformers" in model_lc or model_lc in ("all-minilm-l6-v2", "all-mpnet-base-v2"):
        vec = _local_sentence_transformer(args.model, args.query)
    else:
        sys.exit(
            f"embedding provider for {args.model!r} not implemented; "
            "extend embed_query.py with the right SDK + API key"
        )

    payload = json.dumps({"model": args.model, "dim": len(vec), "vector": vec})
    if args.out:
        Path(args.out).write_text(payload)
    else:
        print(payload)


if __name__ == "__main__":
    main()
