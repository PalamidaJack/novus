"""Portable run bundle exporter for benchmark reproducibility."""

from __future__ import annotations

import hmac
import hashlib
import json
import os
import platform
import subprocess
import sys
from dataclasses import dataclass
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any, Dict, Optional

from novus.runtime.artifacts import RunArtifactLogger
from novus.runtime.manifest import (
    BenchmarkRunManifest,
    MANIFEST_SCHEMA_VERSION,
    ManifestProvenance,
    ManifestSignature,
)
from novus.runtime.replay import RunReplayer


@dataclass
class ExportResult:
    session_id: str
    bundle_dir: Path
    manifest_path: Path
    events_path: Path
    state_path: Optional[Path]


class RunExporter:
    """Exports a run as a self-contained directory bundle."""

    def __init__(
        self,
        artifact_logger: Optional[RunArtifactLogger] = None,
        state_dir: Optional[Path] = None,
        export_dir: Optional[Path] = None,
        signing_key: Optional[str] = None,
    ):
        self.artifact_logger = artifact_logger or RunArtifactLogger()
        self.state_dir = Path(state_dir or Path.home() / ".novus" / "sessions")
        self.export_dir = Path(export_dir or Path.home() / ".novus" / "exports")
        self.replayer = RunReplayer()
        self.signing_key = signing_key or os.getenv("NOVUS_BUNDLE_SIGNING_KEY")

    def export(self, session_id: str) -> ExportResult:
        events = self.artifact_logger.read(session_id)
        if not events:
            raise FileNotFoundError(f"No run events for session: {session_id}")

        bundle_dir = self.export_dir / session_id
        bundle_dir.mkdir(parents=True, exist_ok=True)

        events_path = bundle_dir / "events.jsonl"
        with events_path.open("w", encoding="utf-8") as f:
            for event in events:
                f.write(json.dumps(event, default=str) + "\n")

        state_src = self.state_dir / f"{session_id}.json"
        state_out = bundle_dir / "state.json"
        state_path: Optional[Path] = None
        if state_src.exists():
            state_out.write_text(state_src.read_text(encoding="utf-8"), encoding="utf-8")
            state_path = state_out

        summary = self.replayer.summarize(session_id, events)
        events_sha256 = hashlib.sha256(events_path.read_bytes()).hexdigest()
        provenance = self._build_provenance()

        manifest_data = {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "session_id": session_id,
            "event_count": summary.total_events,
            "turns": summary.turns,
            "tool_calls": summary.tool_calls,
            "errors": summary.errors,
            "final_answer": summary.final_answer,
            "files": {
                "events": events_path.name,
                "state": state_out.name if state_path else None,
            },
            "checksums": {
                "events_sha256": events_sha256,
            },
            "provenance": provenance.model_dump(),
        }
        if self.signing_key:
            digest = self._sign_manifest(manifest_data, self.signing_key)
            manifest_data["signature"] = ManifestSignature(
                algorithm="hmac-sha256",
                digest=digest,
            ).model_dump()

        validated_manifest = BenchmarkRunManifest.model_validate(manifest_data)

        manifest_path = bundle_dir / "manifest.json"
        manifest_path.write_text(validated_manifest.model_dump_json(indent=2), encoding="utf-8")

        return ExportResult(
            session_id=session_id,
            bundle_dir=bundle_dir,
            manifest_path=manifest_path,
            events_path=events_path,
            state_path=state_path,
        )

    def _build_provenance(self) -> ManifestProvenance:
        return ManifestProvenance(
            novus_version=self._get_novus_version(),
            python_version=sys.version.split()[0],
            platform=platform.platform(),
            git_commit=self._git_commit(),
            git_dirty=self._git_dirty(),
            dependency_fingerprint=self._dependency_fingerprint(),
        )

    def _get_novus_version(self) -> str:
        try:
            from novus import __version__
            return str(__version__)
        except Exception:
            return "unknown"

    def _repo_root(self) -> Optional[Path]:
        current = Path(__file__).resolve()
        for parent in current.parents:
            if (parent / ".git").exists():
                return parent
        return None

    def _git_commit(self) -> Optional[str]:
        root = self._repo_root()
        if not root:
            return None
        try:
            out = subprocess.check_output(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            return out or None
        except Exception:
            return None

    def _git_dirty(self) -> Optional[bool]:
        root = self._repo_root()
        if not root:
            return None
        try:
            out = subprocess.check_output(
                ["git", "-C", str(root), "status", "--porcelain"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            return bool(out.strip())
        except Exception:
            return None

    def _dependency_fingerprint(self) -> str:
        try:
            pairs = sorted(
                f"{dist.metadata['Name']}=={dist.version}"
                for dist in importlib_metadata.distributions()
                if dist.metadata and dist.metadata.get("Name")
            )
            digest = hashlib.sha256("\n".join(pairs).encode("utf-8")).hexdigest()
            return digest
        except Exception:
            return hashlib.sha256(b"unknown").hexdigest()

    def _sign_manifest(self, manifest_data: Dict[str, Any], key: str) -> str:
        canonical = json.dumps(manifest_data, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hmac.new(key.encode("utf-8"), canonical, hashlib.sha256).hexdigest()
