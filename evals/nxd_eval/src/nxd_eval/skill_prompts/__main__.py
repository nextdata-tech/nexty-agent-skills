"""Regenerate the vendored prompts from the repository's ``src/``."""

from pathlib import Path

from . import PACKS, render_from_skills

src = Path(__file__).resolve().parents[5] / "src"
if not src.is_dir():
    raise SystemExit(f"skill sources not found at {src}; run from a repository checkout")
out = Path(__file__).with_name(PACKS["nexty-datamesh"])
out.write_text(render_from_skills(src))
print(f"wrote {out}")
