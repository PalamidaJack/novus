"""Typed benchmark manifest schema for portable NOVUS run bundles."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


MANIFEST_SCHEMA_VERSION = "novus-bench-manifest-v1"


class ManifestFiles(BaseModel):
    events: str
    state: Optional[str] = None


class ManifestChecksums(BaseModel):
    events_sha256: str = Field(min_length=64, max_length=64)


class ManifestProvenance(BaseModel):
    novus_version: str
    python_version: str
    platform: str
    git_commit: Optional[str] = None
    git_dirty: Optional[bool] = None
    dependency_fingerprint: str


class ManifestSignature(BaseModel):
    algorithm: Literal["hmac-sha256"]
    digest: str = Field(min_length=64, max_length=64)


class BenchmarkRunManifest(BaseModel):
    schema_version: Literal[MANIFEST_SCHEMA_VERSION] = MANIFEST_SCHEMA_VERSION
    session_id: str
    event_count: int = Field(ge=0)
    turns: int = Field(ge=0)
    tool_calls: int = Field(ge=0)
    errors: int = Field(ge=0)
    final_answer: Optional[str] = None
    files: ManifestFiles
    checksums: ManifestChecksums
    provenance: ManifestProvenance
    signature: Optional[ManifestSignature] = None
