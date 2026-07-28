# Static artifact pitfalls

## Contents

- [Partial catalog fallback](#partial-catalog-fallback)
- [Dropped fields](#dropped-fields)
- [Unsafe HTML](#unsafe-html)
- [Historical releases](#historical-releases)

## Partial catalog fallback

`list_data_products`, `info`, `models`, and `describe_models` are not substitute
inputs. They can make a page look plausible while omitting the complete pinned
schema or release provenance. Fail the artifact when the required bundle cannot
be read.

## Dropped fields

The query-oriented `models` registry is not `data_model`. It may omit
unannotated attributes. Complex types are objects, and one attribute can carry
multiple roles. Ports own their `model_names`/`models`; top-level output arrays
are not their union.

## Unsafe HTML

Payload text can contain markup-like strings. Never concatenate it into HTML or
an attribute. Do not load web fonts or scripts: the artifact must remain useful
offline. A raw JSON tab is both unsafe and outside this artifact's scope.

## Historical releases

An artifact is immutable evidence of its release. On same-workflow rebuild,
discard cached URIs and render the new sequence before any describe/query step.
Do not overwrite the old page or call it current.
