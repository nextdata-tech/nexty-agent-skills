"""Non-text source artifacts handed to the model.

A `MediaInput` is a PDF, an image, or any future modality the API accepts as a
content block. It is deliberately NOT the evidence substring surface — see
`MapperInput.media` versus `MapperInput.landed_text` in `mapper.py`.

Why this module exists rather than a `pdf_bytes` parameter: the API distinguishes
content-block *types*, not just media types. A PDF is `{"type": "document"}` and
an image is `{"type": "image"}`, so serving both is not an enum widening. Naming
the whole path after PDFs also made one codec look like the domain when scanned
pages, screenshots, and photographed forms are the same problem — and the
evidence contract is modality-blind once text has landed (see "Evidence:
two-stage, and what it cannot verify" in the architecture record, which ships in
the repo at docs/architecture/field-mapper.md rather than beside this package).
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from typing import Any
from typing import Literal

from .errors import SpecError

__all__ = [
    "BlockKind",
    "MediaInput",
    "SUPPORTED_MEDIA_TYPES",
    "build_media_content_block",
    "media_digest",
]

BlockKind = Literal["document", "image"]

#: Media types the API accepts, mapped to the content-block type that carries
#: them. An unsupported type is worth rejecting at spec time rather than
#: discovering as a `SCHEMA_REJECT` after paying for the call.
SUPPORTED_MEDIA_TYPES: dict[str, BlockKind] = {
    "application/pdf": "document",
    "image/jpeg": "image",
    "image/png": "image",
    "image/gif": "image",
    "image/webp": "image",
}


@dataclass(frozen=True)
class MediaInput:
    """One non-text artifact sent to the model.

    Exactly one of `data`, `url`, or `file_id` must be set. The choice is a cost
    decision, not a detail: `data` re-sends the bytes on every validation retry
    and is billed each time, while `file_id` uploads once and is referenced. For
    a large document under a retrying spec, that difference dominates the bill.

    **`file_id` is not portable.** The Files API is beta on the first-party Claude
    API and Claude Platform on AWS, and **not supported on Bedrock or Vertex**. So
    the cost-efficient source form for large documents is first-party-only, and a
    spec built around it will fail on a platform it never named. `data` and `url`
    work everywhere. This is a deployment constraint the harness cannot detect
    locally, which is why it is stated here rather than validated.

    `label` is carried into the fence so the model can attribute evidence to a
    specific artifact when several are supplied. It is never trusted as identity
    — the wrong-document defence is `MapperInput.asserted_entity`, checked by
    `reconcile_identity` before mapping.
    """

    media_type: str
    data: bytes | None = None
    url: str | None = None
    file_id: str | None = None
    label: str | None = None
    #: Where `data` was read from, when it came from a file. Carried for
    #: providers that cannot transmit a base64 block and must reference a path
    #: instead (`providers.ClaudeCliProvider`). NEVER part of `media_digest` —
    #: the digest is content-addressed, and letting a path into it would change
    #: `input_snapshot_id` when the fixture moved directory, unbinding every
    #: review for no substantive reason.
    local_path: str | None = None

    def __post_init__(self) -> None:
        forms = [
            name
            for name, value in (
                ("data", self.data),
                ("url", self.url),
                ("file_id", self.file_id),
            )
            if value is not None
        ]
        if len(forms) != 1:
            raise SpecError(
                "a MediaInput carries exactly one of data/url/file_id; got "
                f"{forms or ['none']}. Two source forms for one artifact is "
                "ambiguous about which the model reads and which the snapshot "
                "digest covers."
            )
        if self.media_type not in SUPPORTED_MEDIA_TYPES:
            supported = ", ".join(sorted(SUPPORTED_MEDIA_TYPES))
            raise SpecError(
                f"unsupported media_type {self.media_type!r}; the API accepts "
                f"{supported}. An unsupported type costs a call and returns a "
                "schema reject, so it is refused here instead."
            )
        if self.data is not None and not self.data:
            raise SpecError(
                "MediaInput.data is empty; an empty artifact would be sent as a "
                "valid block and silently judged as if it carried content"
            )

    @property
    def kind(self) -> BlockKind:
        """The API content-block type for this media type."""
        return SUPPORTED_MEDIA_TYPES[self.media_type]

    @property
    def source_form(self) -> Literal["base64", "url", "file_id"]:
        if self.data is not None:
            return "base64"
        if self.url is not None:
            return "url"
        return "file_id"

    def size_bytes(self) -> int | None:
        """Byte size when known locally, else None.

        `url` and `file_id` artifacts are not readable from here, so preflight
        cannot size them. It must say so rather than assume zero — an unsized
        artifact estimated as free is how a budget ceiling gets blown at 60%.
        """
        return len(self.data) if self.data is not None else None


def media_digest(media: MediaInput) -> str:
    """A stable digest of what was read, for `input_snapshot_id`.

    Content hash for local bytes; the reference itself for `url`/`file_id`,
    which is the strongest handle available without fetching. Never the bytes
    themselves — the snapshot is a fingerprint, not a second copy of the source
    (CONTRACT.md §5 on ledger size).

    Media participates in the snapshot because it is part of what was read:
    swapping the image behind a row must unbind that row's reviews exactly as
    editing its landed text does. Omitting media here would let a replaced
    artifact silently inherit a human confirmation.

    Note the asymmetry, which is a real weakness and not an oversight: a `url`
    whose content changes while the URL does not produces an identical digest,
    so reviews will not unbind. Only local bytes give content-addressed
    invalidation.
    """
    if media.data is not None:
        body = hashlib.sha256(media.data).hexdigest()
    elif media.url is not None:
        body = f"url:{media.url}"
    else:
        body = f"file_id:{media.file_id}"
    return f"{media.media_type}:{body}"


def build_media_content_block(media: MediaInput) -> dict[str, Any]:
    """One API content block for this artifact.

    Placed in a USER turn by `build_user_content`, never interpolated into the
    system prompt: source documents are untrusted data, never instruction.
    """
    source: dict[str, Any]
    if media.data is not None:
        source = {
            "type": "base64",
            "media_type": media.media_type,
            # No newlines: the API rejects a wrapped base64 payload.
            "data": base64.standard_b64encode(media.data).decode("ascii"),
        }
    elif media.url is not None:
        source = {"type": "url", "url": media.url}
    else:
        source = {"type": "file_id", "file_id": media.file_id}

    block: dict[str, Any] = {"type": media.kind, "source": source}
    if media.local_path:
        # Underscore-prefixed so it is visibly not an API field. The SDK rejects
        # unknown top-level keys, so `transport` strips it before dispatch; a
        # provider that cannot send base64 reads it instead.
        block["_local_path"] = media.local_path
    return block
