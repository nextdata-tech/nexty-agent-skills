#!/usr/bin/env python3
"""Runner-only fixture materializer and synthetic profile builder."""

from __future__ import annotations
import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
from dataclasses import replace
from pathlib import Path
import sys

repo = os.environ.get("EVAL_NXD_REPO_ROOT")
if repo:
    for source in reversed(
        (
            Path(repo) / "components/nxd_py/data_product",
            Path(repo) / "components/nxd_py/core",
            Path(repo) / "components/nxd_py/drivers",
        )
    ):
        sys.path.insert(0, str(source))

from nxd.experimental.field_mapper import (  # noqa: E402
    EvaluationProfile,
    Grant,
    MapperInput,
    MapperSpec,
    __version__,
)
from nxd.experimental.field_mapper.mapper import system_prompt_for  # noqa: E402
from nxd.experimental.field_mapper.providers import recorded_request_sha256  # noqa: E402
from nxd.experimental.field_mapper.call_adapter import make_call  # noqa: E402
from nxd.experimental.field_mapper.schema import compile_schema  # noqa: E402

WORKFLOW = "terminal-mapper-adapter"
SCHEMA = "nxd-synthetic-evaluation-profile-v1"


def sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _definition_files(root: Path) -> list[tuple[str, bytes]]:
    files = []
    for path in root.rglob("*"):
        if not path.is_file() or path.name == "definition.json":
            continue
        files.append((path.relative_to(root).as_posix(), path.read_bytes()))
    return sorted(files)


def _definition_manifest(root: Path) -> bytes:
    files = _definition_files(root)
    digest = hashlib.sha256()
    digest.update(b"nxd-definition\0")
    digest.update((1).to_bytes(2, "big"))
    manifest_files = []
    for rel, data in files:
        raw = rel.encode()
        digest.update(b"\x01")
        digest.update(len(raw).to_bytes(8, "big"))
        digest.update(raw)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
        manifest_files.append(
            {
                "path": rel,
                "size": str(len(data)),
                "sha256": sha(data),
            }
        )
    definition_id = "sha256-v1:" + digest.hexdigest()
    return (
        json.dumps(
            {
                "schema": "nxd-definition-manifest-v1",
                "definition_id": definition_id,
                "files": manifest_files,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()


def layout_digest(root: Path) -> str:
    entries = []
    for path in sorted(root.rglob("*"), key=lambda x: x.relative_to(root).as_posix()):
        rel = path.relative_to(root).as_posix()
        st = path.lstat()
        if stat.S_ISLNK(st.st_mode):
            raise RuntimeError(f"symlink in starter closure: {rel}")
        if path.is_dir():
            entries.append((0, rel, 0o555, b""))
        elif path.is_file():
            data = (
                _definition_manifest(root)
                if rel == "definition.json"
                else path.read_bytes()
            )
            entries.append((1, rel, 0o444, data))
        else:
            raise RuntimeError(f"unsupported starter entry: {rel}")
    entries.sort(key=lambda x: (x[0], x[1]))
    h = hashlib.sha256()
    h.update(b"nxd-mapper-executable-layout-v1\0")
    for kind, rel, mode, data in entries:
        raw = rel.encode()
        h.update(bytes([kind]))
        h.update(len(raw).to_bytes(8, "big"))
        h.update(raw)
        h.update(mode.to_bytes(4, "big"))
        h.update(len(data).to_bytes(8, "big"))
        h.update(data)
    return "sha256:" + h.hexdigest()


def subject_id(spec_path: Path, grant_path: Path) -> str:
    spec = spec_path.read_bytes()
    grant = grant_path.read_bytes()
    proposal = json.loads(grant)
    fields = (
        "provider",
        "model",
        "corroboration_model",
        "purpose",
        "input_fields",
        "document_classes",
        "pii_category",
        "recurring",
        "expires_at",
        "max_calls",
        "max_tokens",
        "max_usd",
    )
    scope = {key: proposal[key] for key in sorted(fields) if key in proposal}
    payload = {
        "schema": "nxd-mapper-approval-subject-v1",
        "workflow": WORKFLOW,
        "mapper_spec_sha256": sha(spec),
        "proposed_grant_sha256": sha(grant),
        "scope": scope,
    }
    return sha(
        json.dumps(
            payload, ensure_ascii=False, separators=(",", ":"), sort_keys=False
        ).encode()
    )


def request_hashes(root: Path, profile_path: Path) -> list[str]:
    spec = MapperSpec.load(root / "contracts/mapper_spec.json")
    schema = compile_schema(spec)
    bound = replace(spec, wire_schema=schema, harness_version=__version__)
    grant_data = json.loads((root / "contracts/mapper_grant.json").read_text())
    grant_data["mapper_spec_id"] = bound.mapper_spec_id
    grant = Grant.from_dict(grant_data)
    profile = EvaluationProfile.load(profile_path, workspace_root=root)
    call = make_call(spec=bound, grant=grant, evaluation_profile=profile)
    client = call._client_for(spec=bound, corroboration=False)
    hashes = []
    for order_id, category in (("ORD-1001", "freight"), ("ORD-1002", "warehousing")):
        item = MapperInput(
            input_id=order_id,
            identity={"order_id": order_id},
            fields={"order_id": order_id, "product_category": category},
            landed_text=f"Order {order_id} category {category}.",
            document_class="order",
        )
        request = client._build_request(
            system_prompt=system_prompt_for(item),
            instruction=bound.instruction,
            wire_schema=schema,
            text_inputs=[item.landed_text],
            media_inputs=[],
        )
        hashes.append(recorded_request_sha256(request))
    return hashes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    source = Path(__file__).resolve().parent / "reference-closure"
    shutil.copytree(source, args.workspace, dirs_exist_ok=True)
    root = args.workspace
    repo = os.environ.get("EVAL_NXD_REPO_ROOT")
    if not repo:
        raise RuntimeError(
            "EVAL_NXD_REPO_ROOT is required for the NXD admission normalizer"
        )
    compiler = Path(repo) / "components/desktop/supervisor/py/spec_compile.py"
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "EVAL_NXD_REPO_ROOT": repo,
    }
    admitted = subprocess.run(
        [sys.executable, str(compiler), "--admit", str(root), str(root)],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if admitted.returncode != 0:
        raise RuntimeError(
            "NXD admission normalizer failed: "
            + (admitted.stderr.strip() or admitted.stdout.strip() or "unknown error")
        )
    spec_path = root / "contracts/mapper_spec.json"
    grant_path = root / "contracts/mapper_grant.json"
    dummy = {
        "schema": SCHEMA,
        "provider": {
            "kind": "recorded",
            "responses": [
                {
                    "request_sha256": "sha256:" + "0" * 64,
                    "input_tokens": 10,
                    "output_tokens": 10,
                    "stop_reason": "end_turn",
                    "model": "claude-haiku-4-5-20251001",
                    "text": "{}",
                    "provider_notes": [],
                }
            ],
        },
        "approval": {
            "events": [
                {
                    "workflow": WORKFLOW,
                    "subject_id": "sha256:" + "0" * 64,
                    "manifest_sha256": "sha256:" + "0" * 64,
                    "budget_fingerprint": "sha256:" + "0" * 64,
                    "decision": "accepted",
                }
            ]
        },
    }
    temp = args.output.with_suffix(".tmp")
    temp.write_text(json.dumps(dummy))
    temp.chmod(0o444)
    hashes = request_hashes(root, temp)
    definition_manifest = _definition_manifest(root)
    (root / "definition.json").write_bytes(definition_manifest)
    (root / "definition.json").chmod(0o444)
    source = Path(root / "data/orders/orders.csv").read_text()
    responses = []
    for request_hash, category in zip(hashes, ("freight", "warehousing")):
        responses.append(
            {
                "request_sha256": request_hash,
                "input_tokens": 10,
                "output_tokens": 10,
                "stop_reason": "end_turn",
                "model": "claude-haiku-4-5-20251001",
                "text": json.dumps(
                    {
                        "order_category": {
                            "value": category,
                            "evidence": [
                                {
                                    "quote": f"category {category}",
                                    "source_field_name": "order_text",
                                }
                            ],
                        }
                    }
                ),
                "provider_notes": ["evaluation_synthetic"],
            }
        )
    report = {
        "transform_budget_secs": 180,
        "source": "default",
        "min_secs": 5,
        "max_secs": 3600,
        "default_secs": 180,
    }
    budget = sha(json.dumps(report, separators=(",", ":")).encode())
    event = {
        "workflow": WORKFLOW,
        "subject_id": subject_id(spec_path, grant_path),
        "manifest_sha256": layout_digest(root),
        "budget_fingerprint": budget,
        "decision": "accepted",
    }
    final = {
        "schema": SCHEMA,
        "provider": {"kind": "recorded", "responses": responses},
        "approval": {"events": [event]},
    }
    args.output.write_text(json.dumps(final, indent=2) + "\n")
    args.output.chmod(0o444)
    temp.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
