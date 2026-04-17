"""S3 I/O helpers para el paquete rag.

Solo operaciones de lectura/listado (el runtime RAG no escribe en data/).
"""

from __future__ import annotations

import os

import boto3

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client("s3")
    return _client


def get_bucket() -> str:
    bucket = os.environ.get("S3_BUCKET_NAME", "")
    if not bucket:
        raise RuntimeError("S3_BUCKET_NAME no está definida. Agrégala al archivo .env.")
    return bucket


def list_keys(prefix: str, suffix: str = "") -> list[str]:
    """Lista todos los keys bajo *prefix* que terminen en *suffix*, ordenados."""
    paginator = _get_client().get_paginator("list_objects_v2")
    keys: list[str] = []
    for page in paginator.paginate(Bucket=get_bucket(), Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not suffix or key.endswith(suffix):
                keys.append(key)
    return sorted(keys)


def read_text(key: str, encoding: str = "utf-8") -> str:
    """Descarga un objeto S3 y devuelve su contenido como string."""
    response = _get_client().get_object(Bucket=get_bucket(), Key=key)
    return response["Body"].read().decode(encoding)
