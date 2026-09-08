#!/usr/bin/env python3
"""Render one doc in this pack as a self-contained styled HTML page.

Lives beside the docs it renders so a wording change and a rendering change are
one commit in one repo. Its caller is the NXD desktop packager
(`components/desktop/supervisor/scripts/lib/payload.sh`, `stage_docs`), which
consumes this pack as a submodule and stages both forms of the guide into the
offline bundle: the markdown an agent reads, and this page for a browser. The
packager overrides the path with `DOC_RENDERER`; nothing else about the split
matters to it.

Nothing this writes runs anywhere — only the OUTPUT ships.

WHY A RENDERER RATHER THAN A DEPENDENCY:

  * The packager that calls this requires `python3` and NOTHING else at
    payload-composition time. Reaching for `markdown` or `mistune` would add a
    resolve step to a build whose other Python use is stdlib, on a host where
    the wheel closure being resolved is for a DIFFERENT interpreter than the one
    running this.
  * The bundle manifest hashes what this writes, so the output must be
    byte-identical for identical input on every build host. A pinned stdlib
    renderer is that by construction; a floating third-party one is not.

Deliberately NOT a general Markdown implementation. It covers the constructs the
guide uses — ATX headings with GitHub-compatible anchor slugs, pipe
tables, fenced code, blockquotes, ordered/unordered lists, thematic breaks, and
inline code/emphasis/links/images. An unsupported construct renders as its own
literal text rather than silently vanishing, which is the failure mode that
matters for a doc a user reads instead of a program parsing it.

Styling follows nextdata.com: its palette (`--midnight-blue`, `--orange`,
`--dark-slate-blue`, `--off-white`), its type pairing (PP Neue Montreal for
text, Space Mono for code) and its 820px measure. The webfonts are declared
against the site's own CDN with a full fallback stack behind them, so the page
picks up the brand faces when the reader is online and degrades to system faces
when they are not — an offline install must still render, and a bundle cannot
carry a licensed webfont.

A doc's `![](image.png)` is relative to the MARKDOWN, and a browser resolves the
rendered `src` relative to the HTML — so the page is useless without the files
it references sitting beside it in the same arrangement. The output is therefore
a DIRECTORY, not a file: the page plus everything it references, self-contained,
so a caller can hand out the directory (or `-z`'s tarball of it) without knowing
which assets this particular document happens to use.

Usage:
    render_doc_html.py <input.md> [<output-dir>] [-z]

    <output-dir>    where the page and its assets go. Defaults to a directory
                    named after the document, in the current directory.
    -z, --tarball   also write <document>.tar.gz beside the output directory,
                    holding its CONTENTS — unpacking it does not nest them under
                    the directory's name. Named for the document, not the
                    directory: the directory is a working location, the document
                    is what gets handed to someone.
"""

from __future__ import annotations

import argparse
import gzip
import html
import re
import shutil
import sys
import tarfile
from pathlib import Path

# --- nextdata.com palette + type, read off the live stylesheet. -------------
# `:root{--midnight-blue:#262037;--white:white;--dark-slate-blue:#5c487f;
#  --off-white:#f7f7f7;--orange:#ff7e47}`
FONT_CDN = "https://cdn.prod.website-files.com/637df6e90c998d76cd7bbb79"

# A CONSTANT, never `date.today().year`: the manifest hashes this page, so a year
# read from the clock would change the bundle's cohort hash on New Year's Day
# with no source change behind it. Bump it deliberately.
COPYRIGHT_YEAR = "2026"
COPYRIGHT_HOLDER = "Nextdata"

STYLE = f"""
@font-face {{
  font-family: "PP Neue Montreal";
  src: url("{FONT_CDN}/63919a414f2836c641dc08a1_PPNeueMontreal-Regular.woff2") format("woff2");
  font-weight: 400; font-style: normal; font-display: swap;
}}
@font-face {{
  font-family: "PP Neue Montreal";
  src: url("{FONT_CDN}/6650d0b3b6ac15e0e8b93807_ppneuemontreal-medium.otf") format("opentype");
  font-weight: 500; font-style: normal; font-display: swap;
}}
@font-face {{
  font-family: "PP Neue Montreal";
  src: url("{FONT_CDN}/63919a5a4f28360c80dc091f_PPNeueMontreal-Bold.woff2") format("woff2");
  font-weight: 700; font-style: normal; font-display: swap;
}}
@font-face {{
  font-family: "PP Neue Montreal";
  src: url("{FONT_CDN}/63919a5b368c9d36b597c62d_PPNeueMontreal-Italic.woff2") format("woff2");
  font-weight: 400; font-style: italic; font-display: swap;
}}

:root {{
  --midnight-blue: #262037;
  --dark-slate-blue: #5c487f;
  --off-white: #f7f7f7;
  --orange: #ff7e47;
  --white: #fff;
  --rule: #e2e2e2;
  --muted: #6b6478;
  --sans: "PP Neue Montreal", "Neue Montreal", "Helvetica Neue", Helvetica,
    -apple-system, "Segoe UI", Arial, sans-serif;
  --mono: "Space Mono", ui-monospace, SFMono-Regular, "SF Mono", Menlo,
    Consolas, monospace;
}}

* {{ box-sizing: border-box; }}

body {{
  margin: 0;
  background: var(--off-white);
  color: var(--midnight-blue);
  font-family: var(--sans);
  font-size: 17px;
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
}}

/* Two columns: a sticky contents rail, then the measure. The grid is centred as
   a whole rather than centring `main` on its own, so the prose does not shift
   sideways between a doc that has a contents list and one that does not. */
.layout {{
  display: grid;
  grid-template-columns: 232px minmax(0, 820px);
  justify-content: center;
  gap: 56px;
  padding: 0 24px;
}}
.layout-no-toc {{ grid-template-columns: minmax(0, 820px); }}

main {{
  min-width: 0;
  padding: 72px 0 120px;
}}

.toc {{
  position: sticky;
  top: 0;
  align-self: start;
  max-height: 100vh;
  overflow-y: auto;
  padding: 76px 0 32px;
  font-size: 14px;
  line-height: 1.35;
}}
.toc-title {{
  margin: 0 0 12px;
  font-weight: 700;
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
}}
.toc ul {{ margin: 0; padding: 0; list-style: none; }}
.toc li {{ margin: 0; }}
.toc a {{
  display: block;
  padding: 5px 10px;
  border-left: 2px solid var(--rule);
  color: var(--midnight-blue);
  text-decoration: none;
}}
.toc a:hover {{ color: var(--orange); border-left-color: var(--orange); }}
/* Set by the scroll-spy below; harmless when scripting is off. */
.toc a[aria-current="true"] {{
  border-left-color: var(--orange);
  color: var(--dark-slate-blue);
  font-weight: 700;
}}

/* A heading jumped to from the rail must not land under the viewport edge. */
h1, h2, h3 {{ scroll-margin-top: 24px; }}

h1, h2, h3, h4 {{ font-weight: 500; line-height: 1.2; }}
h1 {{
  margin: 0 0 32px;
  font-size: 44px;
  letter-spacing: -0.02em;
}}
h2 {{
  margin: 64px 0 16px;
  padding-top: 24px;
  border-top: 1px solid var(--rule);
  font-size: 30px;
  letter-spacing: -0.01em;
}}
h3 {{ margin: 40px 0 12px; font-size: 21px; font-weight: 700; }}
h4 {{ margin: 28px 0 8px; font-size: 18px; font-weight: 700; }}

p {{ margin: 0 0 18px; }}

a {{ color: var(--dark-slate-blue); text-decoration: underline; text-decoration-thickness: 1px; text-underline-offset: 2px; }}
a:hover {{ color: var(--orange); }}

strong {{ font-weight: 700; }}

hr {{
  border: 0;
  border-top: 1px solid var(--rule);
  margin: 48px 0;
}}

ul, ol {{ margin: 0 0 18px; padding-left: 24px; }}
li {{ margin: 0 0 8px; }}
li > ul, li > ol {{ margin: 8px 0 0; }}

blockquote {{
  margin: 0 0 18px;
  padding: 14px 20px;
  border-left: 4px solid var(--orange);
  background: var(--white);
  color: var(--midnight-blue);
}}
blockquote p {{ margin: 0 0 10px; }}
blockquote p:last-child {{ margin: 0; }}

code {{
  font-family: var(--mono);
  font-size: 0.86em;
  background: var(--white);
  border: 1px solid var(--rule);
  border-radius: 3px;
  padding: 1px 5px;
}}

pre {{
  margin: 0 0 18px;
  padding: 16px 18px;
  overflow-x: auto;
  background: var(--midnight-blue);
  color: var(--off-white);
  border-radius: 4px;
}}
pre code {{
  background: none;
  border: 0;
  padding: 0;
  font-size: 14px;
  line-height: 1.55;
  color: inherit;
}}

.table-scroll {{ overflow-x: auto; margin: 0 0 18px; }}
table {{ border-collapse: collapse; width: 100%; background: var(--white); }}
th, td {{
  border: 1px solid var(--rule);
  padding: 10px 12px;
  text-align: left;
  vertical-align: top;
  font-size: 15px;
}}
th {{ background: var(--off-white); font-weight: 700; }}

img {{ max-width: 100%; height: auto; border: 1px solid var(--rule); border-radius: 4px; }}

.doc-footer {{
  margin-top: 64px;
  padding-top: 20px;
  border-top: 1px solid var(--rule);
  color: var(--muted);
  font-size: 14px;
}}

/* Below the two-column threshold the rail stops being a rail: it stacks above
   the prose, unsticks, and stops reserving a column. */
@media (max-width: 900px) {{
  .layout {{ grid-template-columns: minmax(0, 1fr); gap: 0; }}
  .toc {{
    position: static;
    max-height: none;
    overflow: visible;
    padding: 40px 0 0;
    border-bottom: 1px solid var(--rule);
    padding-bottom: 20px;
  }}
  main {{ padding-top: 32px; }}
}}

@media (max-width: 640px) {{
  main {{ padding: 32px 0 72px; }}
  h1 {{ font-size: 34px; }}
  h2 {{ font-size: 25px; }}
}}

@media print {{
  body {{ background: var(--white); }}
  .layout {{ display: block; padding: 0; }}
  .toc {{ display: none; }}
  main {{ width: auto; max-width: none; padding: 0; }}
  pre {{ background: var(--off-white); color: var(--midnight-blue); border: 1px solid var(--rule); }}
  h2 {{ page-break-after: avoid; }}
}}
"""

# Marks the rail entry for the section currently on screen. Progressive
# enhancement only: with scripting off the rail is a plain list of links, which
# is what it was before this existed. Static text, so the page stays
# byte-reproducible.
TOC_SCRIPT = """<script>
(function () {
  var links = Array.prototype.slice.call(document.querySelectorAll(".toc a[href^='#']"));
  var targets = links
    .map(function (link) {
      return { link: link, section: document.getElementById(decodeURIComponent(link.hash.slice(1))) };
    })
    .filter(function (entry) { return entry.section; });
  if (!targets.length || !window.IntersectionObserver) return;

  var visible = new Set();
  function paint() {
    var current = targets.filter(function (entry) { return visible.has(entry.section); })[0];
    targets.forEach(function (entry) {
      if (entry === current) {
        entry.link.setAttribute("aria-current", "true");
      } else {
        entry.link.removeAttribute("aria-current");
      }
    });
  }
  var observer = new IntersectionObserver(
    function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          visible.add(entry.target);
        } else {
          visible.delete(entry.target);
        }
      });
      paint();
    },
    { rootMargin: "0px 0px -70% 0px" }
  );
  targets.forEach(function (entry) { observer.observe(entry.section); });
})();
</script>
"""

# ---------------------------------------------------------------------------
# Inline
# ---------------------------------------------------------------------------

# Code spans are extracted BEFORE anything else and re-inserted last: their
# content is literal, so `**` or `[` inside one must not be read as markup. The
# placeholder is a character sequence Markdown cannot produce.
_CODE_TOKEN = "\x00CODE{}\x00"

_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_BOLD = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", re.DOTALL)
_ITALIC = re.compile(r"(?<![\w*])\*(?=\S)([^*]+?)(?<=\S)\*(?![\w*])")


def _safe_url(url: str) -> str:
    """Escape a URL for an attribute, refusing schemes a doc has no use for.

    A rendered guide is opened in a browser, so a `javascript:` href in the
    source would execute on click. The bundled doc is reviewed, but this
    renderer is pointed at whatever the packager stages, and refusing here costs
    one comparison.
    """
    lowered = url.strip().lower()
    if lowered.startswith(("javascript:", "data:", "vbscript:")):
        return "#"
    return html.escape(url.strip(), quote=True)


def render_inline(text: str) -> str:
    codes: list[str] = []

    def stash_code(match: re.Match[str]) -> str:
        codes.append(match.group(1))
        return _CODE_TOKEN.format(len(codes) - 1)

    text = re.sub(r"`([^`]+)`", stash_code, text)
    text = html.escape(text, quote=False)

    text = _IMAGE.sub(
        lambda m: f'<img src="{_safe_url(m.group(2))}" alt="{html.escape(m.group(1), quote=True)}">',
        text,
    )
    text = _LINK.sub(
        lambda m: f'<a href="{_safe_url(m.group(2))}">{m.group(1)}</a>',
        text,
    )
    text = _BOLD.sub(lambda m: f"<strong>{m.group(1)}</strong>", text)
    text = _ITALIC.sub(lambda m: f"<em>{m.group(1)}</em>", text)

    for index, code in enumerate(codes):
        text = text.replace(_CODE_TOKEN.format(index), f"<code>{html.escape(code, quote=False)}</code>")
    return text


def slugify(heading: str) -> str:
    """GitHub's heading anchor, so the doc's own table of contents resolves."""
    # Inline markup is not part of the slug: `## **Terms**` anchors as `terms`.
    text = re.sub(r"`([^`]+)`", r"\1", heading)
    text = re.sub(r"\*\*?([^*]+)\*\*?", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = text.strip().lower()
    text = re.sub(r"[^\w\- ]+", "", text, flags=re.UNICODE)
    return text.replace(" ", "-")


# ---------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*$")
_FENCE = re.compile(r"^\s*(```+|~~~+)\s*([\w+-]*)\s*$")
_RULE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
_BULLET = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_ORDERED = re.compile(r"^(\s*)\d+[.)]\s+(.*)$")
_TABLE_DIVIDER = re.compile(r"^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)+\|?\s*$")


def _table_cells(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


class Renderer:
    def __init__(self, lines: list[str]) -> None:
        self.lines = lines
        self.index = 0
        self.out: list[str] = []

    def peek(self) -> str | None:
        return self.lines[self.index] if self.index < len(self.lines) else None

    def run(self) -> list[str]:
        while (line := self.peek()) is not None:
            if not line.strip():
                self.index += 1
            elif _FENCE.match(line):
                self.code_block()
            elif _HEADING.match(line):
                self.heading()
            elif _RULE.match(line):
                self.index += 1
                self.out.append("<hr>")
            elif line.lstrip().startswith(">"):
                self.blockquote()
            elif self.at_table():
                self.table()
            elif _BULLET.match(line) or _ORDERED.match(line):
                self.list_block()
            else:
                self.paragraph()
        return self.out

    # -- leaf blocks --------------------------------------------------------

    def heading(self) -> None:
        match = _HEADING.match(self.lines[self.index])
        assert match is not None
        self.index += 1
        level = len(match.group(1))
        text = match.group(2)
        anchor = slugify(text)
        self.out.append(f'<h{level} id="{html.escape(anchor, quote=True)}">{render_inline(text)}</h{level}>')

    def code_block(self) -> None:
        opening = _FENCE.match(self.lines[self.index])
        assert opening is not None
        marker = opening.group(1)[0] * 3
        self.index += 1
        body: list[str] = []
        while (line := self.peek()) is not None:
            closing = _FENCE.match(line)
            if closing and closing.group(1).startswith(marker) and not closing.group(2):
                self.index += 1
                break
            body.append(line)
            self.index += 1
        language = opening.group(2)
        attribute = f' class="language-{html.escape(language, quote=True)}"' if language else ""
        escaped = html.escape("\n".join(body), quote=False)
        self.out.append(f"<pre><code{attribute}>{escaped}</code></pre>")

    def blockquote(self) -> None:
        # Contiguous `>` lines are ONE quote. A blank `>` line inside it starts a
        # new paragraph within the same quote; an unquoted blank line ends it.
        paragraphs: list[list[str]] = [[]]
        while (line := self.peek()) is not None and line.lstrip().startswith(">"):
            content = line.lstrip()[1:]
            if content.startswith(" "):
                content = content[1:]
            if content.strip():
                paragraphs[-1].append(content)
            elif paragraphs[-1]:
                paragraphs.append([])
            self.index += 1
        rendered = "".join(f"<p>{render_inline(' '.join(chunk))}</p>" for chunk in paragraphs if chunk)
        self.out.append(f"<blockquote>{rendered}</blockquote>")

    def paragraph(self) -> None:
        body: list[str] = []
        while (line := self.peek()) is not None and line.strip():
            if (
                _HEADING.match(line)
                or _FENCE.match(line)
                or _RULE.match(line)
                or line.lstrip().startswith(">")
                or _BULLET.match(line)
                or _ORDERED.match(line)
            ):
                break
            body.append(line.strip())
            self.index += 1
        if body:
            self.out.append(f"<p>{render_inline(' '.join(body))}</p>")

    # -- container blocks ---------------------------------------------------

    def at_table(self) -> bool:
        line = self.peek()
        following = self.lines[self.index + 1] if self.index + 1 < len(self.lines) else ""
        return bool(line and "|" in line and _TABLE_DIVIDER.match(following))

    def table(self) -> None:
        header = _table_cells(self.lines[self.index])
        self.index += 2  # header + divider
        rows: list[list[str]] = []
        while (line := self.peek()) is not None and line.strip() and "|" in line:
            rows.append(_table_cells(line))
            self.index += 1

        width = max([len(header)] + [len(row) for row in rows])

        def cells(values: list[str], tag: str) -> str:
            padded = values + [""] * (width - len(values))
            return "".join(f"<{tag}>{render_inline(value)}</{tag}>" for value in padded)

        body = "".join(f"<tr>{cells(row, 'td')}</tr>" for row in rows)
        self.out.append(
            '<div class="table-scroll"><table>'
            f"<thead><tr>{cells(header, 'th')}</tr></thead>"
            f"<tbody>{body}</tbody>"
            "</table></div>"
        )

    def list_block(self, indent: int = 0) -> None:
        pattern = _ORDERED if _ORDERED.match(self.lines[self.index]) else _BULLET
        tag = "ol" if pattern is _ORDERED else "ul"
        items: list[str] = []
        while (line := self.peek()) is not None:
            if not line.strip():
                # A blank line ends the list unless the next line continues it at
                # this level — which is how the guide separates loose items.
                following = self.lines[self.index + 1] if self.index + 1 < len(self.lines) else ""
                match = pattern.match(following)
                if not match or len(match.group(1)) != indent:
                    break
                self.index += 1
                continue
            match = pattern.match(line)
            if not match:
                other = (_BULLET if pattern is _ORDERED else _ORDERED).match(line)
                if other and len(other.group(1)) == indent:
                    break  # a different list type at this level is a new list
                if line.startswith(" ") and items:
                    items[-1] += " " + render_inline(line.strip())
                    self.index += 1
                    continue
                break
            if len(match.group(1)) < indent:
                break
            if len(match.group(1)) > indent:
                nested_start = len(self.out)
                self.list_block(len(match.group(1)))
                if items:
                    items[-1] += "".join(self.out[nested_start:])
                del self.out[nested_start:]
                continue
            items.append(render_inline(match.group(2)))
            self.index += 1
        rendered = "".join(f"<li>{item}</li>" for item in items)
        self.out.append(f"<{tag}>{rendered}</{tag}>")


def render_blocks(text: str) -> list[str]:
    return Renderer(text.replace("\r\n", "\n").replace("\r", "\n").split("\n")).run()


_H2 = re.compile(r'^<h2 id="([^"]*)">(.*)</h2>$')


def collapse_section_rules(blocks: list[str]) -> list[str]:
    """Drop a thematic break that only restates the section heading below it.

    A guide that writes `---` before every `##` renders TWO horizontal lines in
    this stylesheet — the break itself, then the heading's own top border. The
    break is the redundant one: dropping it keeps a section boundary for a `##`
    that has no `---` above it, whereas dropping the border would leave that
    boundary invisible. Breaks anywhere else are left alone.
    """
    kept: list[str] = []
    for index, block in enumerate(blocks):
        following = blocks[index + 1] if index + 1 < len(blocks) else ""
        if block == "<hr>" and _H2.match(following):
            continue
        kept.append(block)
    return kept


def extract_toc(blocks: list[str]) -> tuple[str, list[str]]:
    """Lift the document's own contents list out of the flow, for the side nav.

    The authored list is preferred over one derived from the headings: it is
    what the writer chose to put in front of a reader, including which sections
    to leave out of it. A doc with no contents section falls back to its `##`
    headings, so the nav is never empty for a doc long enough to have any.

    Returns the nav's inner HTML (empty when there is nothing to show) and the
    blocks with the lifted ones removed.
    """
    for index, block in enumerate(blocks):
        match = _H2.match(block)
        if not match or match.group(1) not in {"contents", "table-of-contents"}:
            continue
        following = blocks[index + 1] if index + 1 < len(blocks) else ""
        if following.startswith("<ul>"):
            return following, blocks[:index] + blocks[index + 2 :]
        # A contents heading with no list under it: drop the heading anyway, so
        # the nav does not compete with an empty section of the same name.
        return "", blocks[:index] + blocks[index + 1 :]

    items = "".join(
        f'<li><a href="#{match.group(1)}">{match.group(2)}</a></li>'
        for match in (_H2.match(block) for block in blocks)
        if match
    )
    return (f"<ul>{items}</ul>" if items else ""), blocks


_SRC_URL = re.compile(r'\bsrc="(?P<url>[^"]*)"')


def referenced_assets(page: str) -> list[str]:
    """Every relative `src` the page needs alongside it, in document order.

    `src` only. A local `href` in these docs points at another Markdown file,
    which this renderer has not rendered and would be a broken link in the
    output directory either way — copying it would put the wrong artifact in the
    distribution rather than fix anything. Anchors, absolute paths and anything
    carrying a scheme need nothing copied.
    """
    seen: list[str] = []
    for match in _SRC_URL.finditer(page):
        url = match.group("url")
        if not url or url.startswith(("#", "/")):
            continue
        if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", url):
            continue
        if url not in seen:
            seen.append(url)
    return seen


def collect_assets(page: str, source_dir: Path, output_dir: Path) -> list[Path]:
    """Copy what the page references into the output directory, same layout.

    The reference in the markdown is relative to the markdown, and a browser
    resolves the one in the page relative to the PAGE — so the page and its
    images have to end up in one directory tree, in the same relative
    arrangement. Copying them here is what lets the caller hand out ONE
    directory (or its tarball) rather than having to know which stray files the
    document happened to reference.

    Relative sub-paths are preserved, so `![](images/x.png)` lands at
    `images/x.png` under the output and the reference in the page needs no
    rewriting. A reference that climbs out of the source directory, or names a
    file that is not there, is reported on stderr and copied nowhere: the page
    still renders, with one visibly missing image, which is a better outcome
    than a directory that quietly is not self-contained.

    Returns the paths written, for the caller to report or archive.
    """
    written: list[Path] = []
    for url in referenced_assets(page):
        relative = Path(url)
        source = source_dir / relative
        if ".." in relative.parts:
            print(
                f"warning: {url} points outside {source_dir} and was not collected",
                file=sys.stderr,
            )
            continue
        if not source.is_file():
            print(f"warning: {url} does not resolve from {source_dir}", file=sys.stderr)
            continue
        destination = output_dir / relative
        # The packager renders a doc in the directory it already staged the
        # asset into, so source and destination are routinely the same file.
        if destination.exists() and source.samefile(destination):
            written.append(destination)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        written.append(destination)
    return written


def build_tarball(output_dir: Path, archive_path: Path) -> Path:
    """Archive the output directory's CONTENTS, not the directory itself.

    Members are `nexty-desktop-user-guide.html` and `start_screen.png`, so
    unpacking drops the page where the caller is rather than nesting it under
    whatever the output directory happened to be called.

    The archive is named for the DOCUMENT, not the directory — the directory is
    a working location the caller picked, while the document is what is being
    handed to someone. It is written beside the directory rather than inside it,
    and excluded from its own members regardless: with `.` as the output
    directory the two coincide, and an archive containing itself would depend on
    the order the tree was walked and grow on every re-run.

    Reproducible: members sorted, and identity and timestamp metadata zeroed, so
    the same directory tars to the same bytes on any machine. The gzip wrapper is
    built by hand for the same reason — `tarfile.open(..., "w:gz")` stamps the
    CURRENT time and the archive's own filename into the gzip header, which alone
    makes two archives of one unchanged directory differ.
    """
    archive_resolved = archive_path.resolve()
    paths = sorted(
        path
        for path in output_dir.rglob("*")
        if path.is_file() and path.resolve() != archive_resolved
    )
    with open(archive_path, "wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                for path in paths:
                    info = archive.gettarinfo(
                        str(path), arcname=str(path.relative_to(output_dir))
                    )
                    info.mtime = 0
                    info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    with open(path, "rb") as handle:
                        archive.addfile(info, handle)
    return archive_path


def document_title(text: str) -> str:
    for line in text.split("\n"):
        match = _HEADING.match(line)
        if match and len(match.group(1)) == 1:
            return re.sub(r"[*`]", "", match.group(2)).strip()
    return "Nexty Desktop"


def render_page(markdown_text: str) -> str:
    title = document_title(markdown_text)
    # Collapse BEFORE extracting: the contents heading usually has a `---` above
    # it too, and dropping the heading first would leave that break behind as the
    # page's opening rule.
    toc, blocks = extract_toc(collapse_section_rules(render_blocks(markdown_text)))
    body = "\n".join(blocks)
    nav = f'<nav class="toc" aria-label="Contents">\n<p class="toc-title">Contents</p>\n{toc}\n</nav>\n' if toc else ""
    # No build timestamp anywhere in here on purpose: the bundle manifest hashes
    # this file, so identical input must produce identical bytes.
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{html.escape(title, quote=False)}</title>\n"
        f"<style>{STYLE}</style>\n"
        "</head>\n<body>\n"
        f'<div class="layout{"" if nav else " layout-no-toc"}">\n'
        f"{nav}"
        "<main>\n"
        f"{body}\n"
        f'<p class="doc-footer">&copy; {COPYRIGHT_YEAR} {COPYRIGHT_HOLDER}</p>\n'
        "</main>\n</div>\n"
        f"{TOC_SCRIPT if nav else ''}"
        "</body>\n</html>\n"
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog=Path(argv[0]).name,
        description="Render a Markdown doc, with everything it references, into one directory.",
    )
    parser.add_argument("source", type=Path, help="the Markdown file to render")
    parser.add_argument(
        "output_dir",
        type=Path,
        nargs="?",
        help="directory to write the page and its assets into, created if absent "
        "(default: a directory named after the document, in the current directory)",
    )
    parser.add_argument(
        "-z",
        "--tarball",
        action="store_true",
        help="also write <document>.tar.gz beside the output directory, holding "
        "its contents without the directory itself",
    )
    args = parser.parse_args(argv[1:])

    source: Path = args.source
    # Default: a directory named after the document, so the common case is one
    # argument and the page still lands somewhere self-contained rather than
    # scattering assets through the caller's working directory.
    output_dir: Path = args.output_dir if args.output_dir is not None else Path(source.stem)
    if not source.is_file():
        print(f"{parser.prog}: {source} is not a file", file=sys.stderr)
        return 2
    if output_dir.exists() and not output_dir.is_dir():
        print(f"{parser.prog}: {output_dir} exists and is not a directory", file=sys.stderr)
        return 2

    output_dir.mkdir(parents=True, exist_ok=True)
    page = render_page(source.read_text(encoding="utf-8"))
    # The page is named after the doc, so a caller pointing two docs at one
    # directory gets both rather than one overwriting the other.
    page_path = output_dir / f"{source.stem}.html"
    page_path.write_text(page, encoding="utf-8")
    assets = collect_assets(page, source.parent, output_dir)

    print(page_path)
    for asset in assets:
        print(asset)
    if args.tarball:
        # Named for the DOCUMENT and placed beside the output directory:
        # `render docs/guide.md -z` yields `guide/` and `guide.tar.gz`, and
        # naming an explicit directory changes where the files go, not what the
        # distributable is called. The parent is taken unresolved so `.` gives
        # `./guide.tar.gz` rather than climbing into the caller's parent.
        archive = output_dir.parent / f"{source.stem}.tar.gz"
        print(build_tarball(output_dir, archive))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
