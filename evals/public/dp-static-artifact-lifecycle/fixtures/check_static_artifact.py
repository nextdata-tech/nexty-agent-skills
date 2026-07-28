#!/usr/bin/env python3
"""Deterministic gate for the real static-artifact wire shape and landed page."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import quote

FIXTURES = Path(__file__).parent
REFERENCE_HTML = (
    Path(__file__).resolve().parents[4]
    / "src/nxd-dp-static-artifact/assets/artifact-example.html"
)
REQUIRED_RELEASE = {
    "workflow",
    "publish_seq",
    "run_id",
    "definition_id",
    "artifact_id",
    "compiler_id",
    "published_at_unix_ms",
}
FORBIDDEN_PAYLOAD_FIELDS = (
    "external_url",
    "environment",
    "full_name",
    "glossary",
    "infra_profile_name",
    "data_product",
    "bearer_token",
    "connection_string",
    "password",
    "driver_type",
    "release_id",
)


def load(fixtures: Path, name: str):
    return json.loads((fixtures / name).read_text(encoding="utf-8"))


def valid_bundle(current: dict, verified: dict, outputs: dict) -> bool:
    workflow = current.get("workflow")
    publish_seq = current.get("publish_seq")
    if not isinstance(workflow, str) or not isinstance(publish_seq, int):
        return False
    expected_release_uri = (
        f"nxd://data-products/{quote(workflow, safe='')}/releases/"
        f"{publish_seq}/verified.json"
    )
    if current.get("release_uri") != expected_release_uri:
        return False
    if verified.get("schema") != "nxd-desktop-verified-v1":
        return False
    if verified.get("schema") != outputs.get("schema"):
        return False
    if verified.get("trust") != "artifact_verified":
        return False
    if verified.get("trust") != outputs.get("trust"):
        return False

    release = verified.get("release")
    if not isinstance(release, dict):
        return False
    if not REQUIRED_RELEASE.issubset(release) or "release_id" in release:
        return False
    if release.get("workflow") != current.get("workflow"):
        return False
    if release.get("publish_seq") != current.get("publish_seq"):
        return False
    if outputs.get("workflow") != current.get("workflow"):
        return False
    if outputs.get("publish_seq") != current.get("publish_seq"):
        return False
    if any(
        current.get(key) != release.get(key)
        for key in ("definition_id", "artifact_id")
    ):
        return False

    display_models = verified.get("data_model", {}).get("models")
    semantic = verified.get("models", {})
    semantic_models = semantic.get("models")
    joins = semantic.get("joins")
    if not all(isinstance(value, list) for value in (display_models, semantic_models, joins)):
        return False

    model_fields: dict[str, set[str]] = {}
    for model in display_models:
        name = model.get("name")
        attributes = model.get("attributes")
        if not isinstance(name, str) or not isinstance(attributes, list) or name in model_fields:
            return False
        fields = {attribute.get("name") for attribute in attributes}
        if None in fields or len(fields) != len(attributes):
            return False
        model_fields[name] = fields

    for model in semantic_models:
        name = model.get("name")
        if name not in model_fields:
            return False
        for field in model.get("fields", []):
            column = field.get("column")
            if (
                column not in model_fields[name]
                or not isinstance(field.get("roles"), list)
                or not field["roles"]
            ):
                return False
            for role in field["roles"]:
                if role.get("kind") != "join":
                    continue
                target_model = role.get("to_model")
                target_column = role.get("to_column") or column
                if role.get("to_data_product"):
                    if not target_model or not target_column:
                        return False
                elif (
                    target_model not in model_fields
                    or target_column not in model_fields[target_model]
                ):
                    return False

    for join in joins:
        left, right = join.get("left"), join.get("right")
        if left not in model_fields or not right:
            return False
        semantic_left = next(
            (model for model in semantic_models if model.get("name") == left),
            None,
        )
        if semantic_left is None:
            return False
        cross_product = bool(join.get("to_data_product"))
        if not cross_product and right not in model_fields:
            return False
        pairs = join.get("on")
        if not isinstance(pairs, list):
            return False
        for pair in pairs:
            if not isinstance(pair, list) or len(pair) != 2:
                return False
            left_column, right_column = pair
            if left_column not in model_fields[left]:
                return False
            if not cross_product and right_column not in model_fields[right]:
                return False
            semantic_field = next(
                (
                    field
                    for field in semantic_left.get("fields", [])
                    if field.get("column") == left_column
                ),
                None,
            )
            if semantic_field is None or not any(
                role.get("kind") == "join"
                and role.get("to_model") == right
                and (role.get("to_column") or left_column) == right_column
                and role.get("cardinality", "many_to_one")
                == join.get("cardinality", "many_to_one")
                and role.get("to_data_product") == join.get("to_data_product")
                for role in semantic_field["roles"]
            ):
                return False

    output_block = outputs.get("outputs", {})
    top_names = output_block.get("model_names")
    top_models = output_block.get("models")
    if not isinstance(top_names, list) or not isinstance(top_models, list):
        return False
    top_object_names = [
        model.get("name") for model in top_models if isinstance(model, dict)
    ]
    if len(top_object_names) != len(top_models) or top_object_names != top_names:
        return False
    if any(name not in model_fields for name in top_names):
        return False

    ports = output_block.get("ports")
    if not isinstance(ports, list):
        return False
    for port in ports:
        names = port.get("model_names")
        models = port.get("models")
        if not isinstance(names, list) or not isinstance(models, list):
            return False
        object_names = [model.get("name") for model in models if isinstance(model, dict)]
        if len(object_names) != len(models) or object_names != names:
            return False
        if any(name not in model_fields for name in names):
            return False
        promises = port.get("promises")
        if promises is None:
            continue
        if any(name not in model_fields for name in promises.get("model", [])):
            return False
        for custom in promises.get("custom", []):
            if any(name not in model_fields for name in custom.get("models", [])):
                return False
    return True


def bridge_document(payload: dict) -> dict:
    """The sealed document a `read_data_product_resource` result carries.

    The bridge returns a `ReadResourceResult` shape, so the document is the
    parsed `text` of its single content — not the envelope.
    """
    contents = payload["contents"]
    assert len(contents) == 1, contents
    return json.loads(contents[0]["text"])


def valid_superseded_redirect(current: dict, error: dict) -> bool:
    data = error.get("data", {})
    requested = data.get("requested_publish_seq")
    current_seq = data.get("current_publish_seq")
    if error.get("code") != -32002 or not isinstance(requested, int):
        return False
    if current_seq != current.get("publish_seq") or requested == current_seq:
        return False
    expected_uri = (
        f"nxd://data-products/{quote(current['workflow'], safe='')}/releases/"
        f"{current_seq}/verified.json"
    )
    return data.get("current_uri") == expected_uri


def assert_html(html_path: Path) -> None:
    html = html_path.read_text(encoding="utf-8").lower()
    positions = [
        html.index(part)
        for part in (
            "model overview",
            "complete schema",
            "joins",
            "output ports",
            "evidence",
            "release provenance",
            "diagnostics",
        )
    ]
    assert positions == sorted(positions)
    for field in (
        "loyalty_points",
        "profile",
        "amount_usd",
        "primary_key",
        "average_order_value",
        "many_to_one",
        "classification",
        "min: 0",
        "nullable: false",
        "decimal128",
        "output-level models",
        "empty-declaration",
        "freshness &lt; 24h",
        "null · the manifest didn’t say",
        "[] · none declared",
    ):
        assert field in html, field
    assert "customer health &lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert" not in html
    assert "<details><summary>release provenance" in html
    assert "<details><summary>diagnostics" in html
    assert "customer%2fhealth" in html
    assert "nxd://data-products/customer/health/" not in html
    for field in FORBIDDEN_PAYLOAD_FIELDS:
        assert field not in html, field
    for remote in ("<link ", "@import", "http://", "https://"):
        assert remote not in html, remote


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, default=FIXTURES)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--trace", type=Path)
    args = parser.parse_args()

    current = load(args.fixtures, "current.json")
    verified = load(args.fixtures, "verified.json")
    outputs = load(args.fixtures, "outputs.json")
    assert valid_bundle(current, verified, outputs)
    assert valid_superseded_redirect(
        current, load(args.fixtures, "requested-release-1.json")
    )
    assert not valid_bundle(current, verified, load(args.fixtures, "mismatch.json"))
    assert not valid_bundle(current, load(args.fixtures, "missing-release.json"), outputs)

    # Transport equivalence. The bridge tools exist for clients that expose no
    # MCP resource primitives; they are only safe because they read the same
    # sealed bytes through the same reader.
    bridged_verified = bridge_document(load(args.fixtures, "bridge-read-verified.json"))
    assert bridged_verified == verified, "bridge read must deliver the identical document"
    assert valid_bundle(current, bridged_verified, outputs), (
        "a bundle assembled over the bridge validates exactly like a native one"
    )

    # ...and the corollary that makes the fallback rule testable: the bridge is
    # NOT an escape from a domain error. Reading the superseded release through
    # it returns the same redirect, so an agent that "fell back" to dodge the
    # supersession still cannot render release 1.
    bridged_release_1 = load(args.fixtures, "bridge-read-release-1.json")
    assert valid_superseded_redirect(current, bridged_release_1), (
        "bridge preserves the supersession redirect verbatim"
    )
    native_release_1 = load(args.fixtures, "requested-release-1.json")
    contract_fields = ("code", "message", "data")
    assert all(
        bridged_release_1[key] == native_release_1[key] for key in contract_fields
    ), "bridge and resource errors are indistinguishable"

    if args.root:
        candidates = sorted(args.root.glob("*release-17.html"))
        assert len(candidates) == 1, f"expected one landed release HTML, found {candidates}"
        html_path = candidates[0]
    else:
        html_path = REFERENCE_HTML
    assert_html(html_path)
    print("STATIC ARTIFACT GATE PASSED")
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
