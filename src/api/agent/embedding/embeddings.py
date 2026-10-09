"""Vectors for the Pinecone invoice index.

Same model as before (all-MiniLM-L6-v2, 384 dims) via ONNX.
PyTorch and sentence-transformers are not imported: they use more than
Render's 512Mi limit while the API is still starting.
"""

import os
from functools import lru_cache

_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def _model():
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=_MODEL)


def embed_query(text: str) -> list[float]:
    vector = next(_model().embed([text]))
    return vector.tolist()
