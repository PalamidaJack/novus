"""Verification of portable run bundles (checksums + optional signature)."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from novus.runtime.manifest import BenchmarkRunManifest


@dataclass
class VerificationResult:
    ok: bool
    session_id: str
    checksum_ok: bool
    signature_ok: Optional[bool]
    errors: List[str] = field(default_factory=list)


class RunBundleVerifier:
    def verify(self, bundle_dir: Path, signing_key: Optional[str] = None) -> VerificationResult:
        manifest_path = bundle_dir / "manifest.json"
        if not manifest_path.exists():
            return VerificationResult(
                ok=False,
                session_id="unknown",
                checksum_ok=False,
                signature_ok=None,
                errors=["manifest.json not found"],
            )

        manifest_raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = BenchmarkRunManifest.model_validate(manifest_raw)

        events_path = bundle_dir / manifest.files.events
        if not events_path.exists():
            return VerificationResult(
                ok=False,
                session_id=manifest.session_id,
                checksum_ok=False,
                signature_ok=None,
                errors=[f"events file missing: {manifest.files.events}"],
            )

        actual_checksum = hashlib.sha256(events_path.read_bytes()).hexdigest()
        checksum_ok = actual_checksum == manifest.checksums.events_sha256
        errors: List[str] = []
        if not checksum_ok:
            errors.append("events checksum mismatch")

        signature_ok: Optional[bool] = None
        if manifest.signature is not None:
            if not signing_key:
                signature_ok = False
                errors.append("signature present but no signing key provided")
            else:
                canonical_payload = self._canonical_manifest_without_signature(manifest_raw)
                expected = hmac.new(
                    signing_key.encode("utf-8"),
                    canonical_payload.encode("utf-8"),
                    hashlib.sha256,
                ).hexdigest()
                signature_ok = hmac.compare_digest(expected, manifest.signature.digest)
                if not signature_ok:
                    errors.append("manifest signature mismatch")

        ok = checksum_ok and (signature_ok is not False)
        return VerificationResult(
            ok=ok,
            session_id=manifest.session_id,
            checksum_ok=checksum_ok,
            signature_ok=signature_ok,
            errors=errors,
        )

    def _canonical_manifest_without_signature(self, manifest_raw: dict) -> str:
        payload = dict(manifest_raw)
        payload.pop("signature", None)
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))
