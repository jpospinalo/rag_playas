"""S3 I/O helpers para el paquete ingest.

Todas las operaciones son relativas al bucket definido en S3_BUCKET_NAME.
Convención de keys: prefijos sin slash inicial, con slash al final ("raw/", "silver/").
"""

from __future__ import annotations

import os
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

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


def key_exists(key: str) -> bool:
    """Devuelve True si el objeto S3 existe."""
    try:
        _get_client().head_object(Bucket=get_bucket(), Key=key)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey"):
            return False
        raise


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


def read_bytes(key: str) -> bytes:
    """Descarga un objeto S3 y devuelve los bytes crudos."""
    response = _get_client().get_object(Bucket=get_bucket(), Key=key)
    return response["Body"].read()


def write_text(key: str, content: str, encoding: str = "utf-8") -> None:
    """Sube un string como objeto S3."""
    _get_client().put_object(
        Bucket=get_bucket(),
        Key=key,
        Body=content.encode(encoding),
    )


def write_bytes(key: str, data: bytes) -> None:
    """Sube bytes como objeto S3."""
    _get_client().put_object(Bucket=get_bucket(), Key=key, Body=data)


def download_file(key: str, local_path: str) -> None:
    """Descarga un objeto S3 a un archivo local (usado por pdf_to_md)."""
    _get_client().download_file(Bucket=get_bucket(), Key=key, Filename=local_path)


def upload_file(local_path: str, key: str) -> None:
    """Sube un archivo local a S3 (usado por pdf_to_md tras Docling)."""
    _get_client().upload_file(Filename=local_path, Bucket=get_bucket(), Key=key)


def upload_directory(local_dir: str, prefix: str) -> None:
    """Sube recursivamente todos los archivos de *local_dir* a S3 bajo *prefix*.

    El key de cada archivo es: prefix + ruta relativa desde local_dir.
    """
    local_root = Path(local_dir)
    for local_file in local_root.rglob("*"):
        if local_file.is_file():
            relative = local_file.relative_to(local_root)
            key = prefix + relative.as_posix()
            upload_file(str(local_file), key)
