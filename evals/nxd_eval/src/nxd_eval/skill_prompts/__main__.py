"""Regenerate the vendored prompts from ``src/``; run from the repository root."""

from pathlib import Path

from . import PACKS, render_from_skills

out = Path(__file__).with_name(PACKS["nexty-datamesh"])
out.write_text(render_from_skills(Path.cwd() / "src"))
print(f"wrote {out}")
