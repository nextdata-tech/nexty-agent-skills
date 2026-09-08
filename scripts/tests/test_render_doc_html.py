"""Guards for `scripts/render_doc_html.py`, the pack's doc-to-HTML renderer.

WHY THESE LIVE HERE. The renderer's only consumer is in another repository — the
NXD desktop packager stages both forms of a doc into its offline installer and
hashes the rendered page into the bundle manifest — and it reaches this file
across a submodule pin. So a rendering regression committed here is invisible
until someone bumps that pin, at which point it surfaces over there as a
packaging or install failure with nothing pointing back at this commit. These
tests move that failure to the change that causes it.

They pin BEHAVIOUR a reader or the consumer depends on, not the renderer's
internals: reproducible bytes, the anchors a Markdown table of contents links
to, one rule per section boundary, the side nav, escaping, and the fact that the
file is where its caller looks for it. Stdlib + pytest only, matching the
validator this repo already runs with no environment of its own.
"""

from __future__ import annotations

import importlib.util
import re
import tarfile
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RENDERER_PATH = REPO_ROOT / "scripts" / "render_doc_html.py"

# The path the NXD packager resolves by default (`DOC_RENDERER` in
# components/desktop/supervisor/scripts/lib/payload.sh). Named here so a rename
# on this side fails with the reason rather than as a missing file over there.
CONSUMER_DEFAULT_PATH = "external/nexty-agent-skills/scripts/render_doc_html.py"


def _load_renderer() -> ModuleType:
    """Import the script by path — `scripts/` is not a package."""
    spec = importlib.util.spec_from_file_location("render_doc_html", RENDERER_PATH)
    assert spec is not None and spec.loader is not None, f"cannot load {RENDERER_PATH}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


renderer = _load_renderer()


def render(markdown: str) -> str:
    return renderer.render_page(markdown)


def prose_of(page: str) -> str:
    """Everything after `<main>` — the document body, excluding the side nav."""
    return page.split("<main>", 1)[1]


def nav_of(page: str) -> str:
    """The side nav's markup, or an empty string when the page has none."""
    if '<nav class="toc"' not in page:
        return ""
    return page.split('<nav class="toc"', 1)[1].split("</nav>", 1)[0]


# ---------------------------------------------------------------------------
# The contract with the consumer
# ---------------------------------------------------------------------------


def test_the_renderer_is_where_its_consumer_looks_for_it() -> None:
    """A rename here is a broken build in the repo that calls this."""
    assert RENDERER_PATH.is_file(), (
        f"{RENDERER_PATH} is missing; the NXD desktop packager resolves it as "
        f"{CONSUMER_DEFAULT_PATH} and refuses to package without it"
    )
    assert CONSUMER_DEFAULT_PATH.endswith(
        f"scripts/{RENDERER_PATH.name}"
    ), "the consumer's default path no longer names this file"


def test_identical_input_renders_identical_bytes() -> None:
    """The consumer hashes this output into a bundle manifest.

    A page that differed between two renders of one source would make that
    manifest unreproducible, and an installer that verifies it would reject a
    bundle nobody changed.
    """
    source = "# Title\n\n## Section\n\nBody text.\n"
    assert render(source) == render(source)


def test_the_renderer_never_reads_the_clock() -> None:
    """The copyright year is a constant for the reason above.

    `date.today().year` would rotate the rendered page — and so the bundle's
    cohort hash — on New Year's Day with no source change behind it. The
    determinism test above cannot see that: both of its renders happen in the
    same second.
    """
    # `#`-comments are stripped first: the renderer's own comment explains why it
    # does not read the clock, and naming the calls there must not trip this.
    code = "\n".join(
        line for line in RENDERER_PATH.read_text().splitlines() if not line.lstrip().startswith("#")
    )
    offenders = re.findall(r"date\.today|datetime\.now|time\.time", code)
    assert not offenders, f"the renderer reads the clock: {sorted(set(offenders))}"


def test_the_page_carries_a_copyright_and_no_build_provenance() -> None:
    page = render("# Title\n\nBody.\n")
    assert f"&copy; {renderer.COPYRIGHT_YEAR} {renderer.COPYRIGHT_HOLDER}" in page
    # The footer once named the source file it was rendered from. That is build
    # detail in a document handed to a reader, and it dated the page.
    assert "rendered from" not in page


# ---------------------------------------------------------------------------
# Anchors — what a Markdown table of contents links to
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("heading", "anchor"),
    [
        ("Quickstart", "quickstart"),
        ("How it works", "how-it-works"),
        ("Phase 1: Bring a job to be done", "phase-1-bring-a-job-to-be-done"),
        ("Measures and dimensions", "measures-and-dimensions"),
        ("Standing rules vs. filters", "standing-rules-vs-filters"),
        ("**Terms**", "terms"),
        ("`code` in a heading", "code-in-a-heading"),
    ],
)
def test_heading_anchors_match_githubs_slug(heading: str, anchor: str) -> None:
    """Docs are written and reviewed on GitHub, so their own `#links` are
    GitHub-shaped. An anchor derived any other way silently dead-links every
    contents entry in the document."""
    assert renderer.slugify(heading) == anchor


def test_every_doc_in_the_pack_renders_with_no_dangling_internal_link() -> None:
    """Renders the real docs, not a fixture.

    This is the assertion that catches a slug change: every in-page `#link` a
    doc writes must resolve to a heading id the renderer emitted. A fixture can
    only pin the cases someone thought of; the docs carry the ones writers
    actually write.
    """
    docs = sorted((REPO_ROOT / "docs").rglob("*.md"))
    assert docs, "no docs found to render — this sweep would pass vacuously"
    for doc in docs:
        page = render(doc.read_text(encoding="utf-8"))
        ids = set(re.findall(r'id="([^"]+)"', page))
        targets = {link[1:] for link in re.findall(r'href="(#[^"]+)"', page)}
        assert not targets - ids, f"{doc}: links to missing anchors {sorted(targets - ids)}"


# ---------------------------------------------------------------------------
# Section boundaries
# ---------------------------------------------------------------------------


def test_a_break_directly_above_a_section_heading_is_dropped() -> None:
    """A `---` before every `##` is the house style in these docs, and the
    heading already carries its own rule — so keeping both drew two lines at
    every section boundary."""
    page = render("# Title\n\nIntro.\n\n---\n\n## Section\n\nBody.\n")
    assert "<hr>" not in prose_of(page)
    assert '<h2 id="section">' in prose_of(page)


def test_a_break_between_paragraphs_is_kept() -> None:
    """The break is dropped for restating a boundary, not for being a break."""
    assert "<hr>" in prose_of(render("# Title\n\nOne.\n\n---\n\nTwo.\n"))


# ---------------------------------------------------------------------------
# The side nav
# ---------------------------------------------------------------------------


def test_the_authored_contents_list_becomes_the_nav_and_leaves_the_prose() -> None:
    """The writer's own list is preferred over one derived from the headings:
    it is what they chose to put in front of a reader. It must appear once —
    in the rail, not also mid-document."""
    page = render(
        "# Title\n\n## Contents\n\n- [First](#first)\n- [Second](#second)\n\n"
        "## First\n\nOne.\n\n## Second\n\nTwo.\n"
    )
    assert '<a href="#first">First</a>' in nav_of(page)
    assert 'id="contents"' not in prose_of(page)
    assert "First" in prose_of(page)


def test_a_doc_without_a_contents_section_gets_a_nav_from_its_headings() -> None:
    page = render("# Title\n\n## First\n\nOne.\n\n## Second\n\nTwo.\n")
    nav = nav_of(page)
    assert '<a href="#first">First</a>' in nav
    assert '<a href="#second">Second</a>' in nav


def test_a_doc_with_no_sections_renders_without_a_nav_column() -> None:
    """A one-section note gets the full measure rather than an empty rail."""
    page = render("# Title\n\nJust a paragraph.\n")
    assert nav_of(page) == ""
    assert "layout-no-toc" in page


def test_a_contents_heading_with_no_list_leaves_neither_a_nav_nor_a_stub() -> None:
    page = render("# Title\n\n## Contents\n\n## First\n\nOne.\n")
    assert nav_of(page) == ""
    assert 'id="contents"' not in prose_of(page)


# ---------------------------------------------------------------------------
# Inline and block constructs
# ---------------------------------------------------------------------------


def test_markup_inside_a_code_span_stays_literal() -> None:
    """Code spans are lifted out before any other inline rule runs; a doc
    documenting Markdown or a shell flag depends on it."""
    prose = prose_of(render("# T\n\nUse `**not bold**` and `[not a link](x)`.\n"))
    assert "<code>**not bold**</code>" in prose
    assert "<code>[not a link](x)</code>" in prose
    assert "<strong>" not in prose


def test_prose_that_looks_like_html_is_escaped() -> None:
    prose = prose_of(render("# T\n\nPass <script>alert(1)</script> to it.\n"))
    assert "<script>" not in prose
    assert "&lt;script&gt;" in prose


def test_a_javascript_url_is_neutralised() -> None:
    """The rendered page is opened in a browser, and this renderer runs over
    whatever doc it is pointed at."""
    prose = prose_of(render("# T\n\n[click](javascript:alert(1))\n"))
    assert "javascript:" not in prose
    assert '<a href="#">click</a>' in prose


def test_the_constructs_the_docs_use_survive_a_round_trip() -> None:
    prose = prose_of(
        render(
            "# T\n\n"
            "## Section\n\n"
            "Text with **bold**, *italic* and `code`.\n\n"
            "> A quoted prompt.\n\n"
            "```\ncmd --flag\n```\n\n"
            "- first\n- second\n\n"
            "1. one\n2. two\n\n"
            "| Column | Meaning |\n| --- | --- |\n| `a` | first |\n\n"
            "![shot](shot.png)\n"
        )
    )
    for fragment in (
        "<strong>bold</strong>",
        "<em>italic</em>",
        "<code>code</code>",
        "<blockquote><p>A quoted prompt.</p></blockquote>",
        "<pre><code>cmd --flag</code></pre>",
        "<ul><li>first</li><li>second</li></ul>",
        "<ol><li>one</li><li>two</li></ol>",
        "<th>Column</th>",
        '<img src="shot.png" alt="shot">',
    ):
        assert fragment in prose, f"missing {fragment}"


# ---------------------------------------------------------------------------
# One directory: the page plus what it references
# ---------------------------------------------------------------------------


def _doc_with_an_image(directory: Path, url: str = "shot.png") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    asset = directory / url
    asset.parent.mkdir(parents=True, exist_ok=True)
    asset.write_bytes(b"not-really-a-png")
    doc = directory / "guide.md"
    doc.write_text(f"# T\n\n![shot]({url})\n", encoding="utf-8")
    return doc


def test_the_output_directory_holds_the_page_and_its_assets(tmp_path: Path) -> None:
    """The whole point of taking a directory rather than a filename.

    A caller handed one page and told to find its images themselves is a caller
    who ships a broken page — which is how this interface was found. Rendering
    docs/guide.md into output/ must make output/ self-contained.
    """
    doc = _doc_with_an_image(tmp_path / "docs")
    out = tmp_path / "output"
    assert renderer.main(["render_doc_html.py", str(doc), str(out)]) == 0

    page = out / "guide.html"
    assert page.is_file(), "the page is named after the doc"
    assert (out / "shot.png").is_file(), "the referenced image was not collected"
    # The reference is unchanged, and resolves from the page's own directory —
    # which is the only thing a browser will do with it.
    src = re.search(r'<img src="([^"]+)"', page.read_text(encoding="utf-8"))
    assert src is not None and src.group(1) == "shot.png"
    assert (page.parent / src.group(1)).is_file()


def test_a_nested_asset_keeps_its_relative_place(tmp_path: Path) -> None:
    """`![](images/x.png)` must land at `images/x.png` under the output, or the
    reference in the page would have to be rewritten to find it."""
    doc = _doc_with_an_image(tmp_path / "docs", url="images/shot.png")
    out = tmp_path / "output"
    assert renderer.main(["render_doc_html.py", str(doc), str(out)]) == 0
    assert (out / "images" / "shot.png").is_file()
    assert 'src="images/shot.png"' in (out / "guide.html").read_text(encoding="utf-8")


def test_the_output_directory_is_created(tmp_path: Path) -> None:
    doc = _doc_with_an_image(tmp_path / "docs")
    out = tmp_path / "does" / "not" / "exist"
    assert renderer.main(["render_doc_html.py", str(doc), str(out)]) == 0
    assert (out / "guide.html").is_file()


def test_rendering_in_place_leaves_the_asset_alone(tmp_path: Path) -> None:
    """The packager's case: it stages the doc and its assets first, then renders
    in that same directory, so every copy is a file onto itself."""
    doc = _doc_with_an_image(tmp_path / "docs")
    before = (doc.parent / "shot.png").read_bytes()
    assert renderer.main(["render_doc_html.py", str(doc), str(doc.parent)]) == 0
    assert (doc.parent / "shot.png").read_bytes() == before
    assert 'src="shot.png"' in (doc.parent / "guide.html").read_text(encoding="utf-8")


def test_a_missing_asset_is_reported(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The page still renders — one visible gap beats a directory that quietly
    is not self-contained."""
    doc = tmp_path / "docs" / "guide.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("# T\n\n![gone](gone.png)\n", encoding="utf-8")
    out = tmp_path / "output"
    assert renderer.main(["render_doc_html.py", str(doc), str(out)]) == 0
    assert (out / "guide.html").is_file()
    assert "does not resolve" in capsys.readouterr().err


def test_an_asset_outside_the_source_directory_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Collecting `../../secrets.png` would write outside the output tree."""
    (tmp_path / "outside.png").write_bytes(b"x")
    doc = tmp_path / "docs" / "guide.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("# T\n\n![out](../outside.png)\n", encoding="utf-8")
    out = tmp_path / "output"
    assert renderer.main(["render_doc_html.py", str(doc), str(out)]) == 0
    assert not (out / "outside.png").exists()
    assert not (tmp_path / "output.png").exists()
    assert "points outside" in capsys.readouterr().err


@pytest.mark.parametrize("url", ["#anchor", "/absolute/path.png", "https://example.com/x.png"])
def test_references_that_need_no_local_file_are_not_collected(url: str) -> None:
    assert renderer.referenced_assets(f'<img src="{url}">') == []


def test_the_brand_webfont_urls_are_not_treated_as_assets() -> None:
    """The stylesheet's font URLs are in the page too; collecting them would try
    to copy a nonexistent local file on every render."""
    assert renderer.referenced_assets(render("# T\n\nBody.\n")) == []


# ---------------------------------------------------------------------------
# -z, the distributable tarball
# ---------------------------------------------------------------------------


def test_the_output_directory_defaults_to_the_documents_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One argument is the common case: render a doc, get a directory.

    Defaulting to the document's name rather than the working directory keeps
    the output self-contained instead of scattering a page and its assets
    through wherever the caller happened to be standing.
    """
    doc = _doc_with_an_image(tmp_path / "docs")
    monkeypatch.chdir(tmp_path)
    assert renderer.main(["render_doc_html.py", str(doc)]) == 0
    assert (tmp_path / "guide" / "guide.html").is_file()
    assert (tmp_path / "guide" / "shot.png").is_file()


def test_the_tarball_is_named_for_the_document_not_the_directory(tmp_path: Path) -> None:
    """The directory is a working location the caller picked; the document is
    what gets handed to someone, so it names the distributable."""
    doc = _doc_with_an_image(tmp_path / "docs")
    assert renderer.main(["render_doc_html.py", str(doc), str(tmp_path / "whatever"), "-z"]) == 0
    assert (tmp_path / "guide.tar.gz").is_file()
    assert not (tmp_path / "whatever.tar.gz").exists()


def test_the_tarball_holds_the_contents_not_the_directory(tmp_path: Path) -> None:
    """`-z` must unpack AS the page and its assets, not nested under the output
    directory — that is what makes it a distributable."""
    doc = _doc_with_an_image(tmp_path / "docs")
    out = tmp_path / "output"
    assert renderer.main(["render_doc_html.py", str(doc), str(out), "-z"]) == 0

    with tarfile.open(tmp_path / "guide.tar.gz") as opened:
        members = sorted(opened.getnames())
    assert members == ["guide.html", "shot.png"]
    assert not any(name.startswith(("output", "guide/")) for name in members)


def test_the_tarball_is_written_beside_the_directory_not_inside_it(tmp_path: Path) -> None:
    doc = _doc_with_an_image(tmp_path / "docs")
    out = tmp_path / "output"
    renderer.main(["render_doc_html.py", str(doc), str(out), "-z"])
    assert not list(out.glob("*.tar.gz"))
    # A second run archives the same two members, not the previous archive.
    renderer.main(["render_doc_html.py", str(doc), str(out), "-z"])
    with tarfile.open(tmp_path / "guide.tar.gz") as opened:
        assert sorted(opened.getnames()) == ["guide.html", "shot.png"]


def test_a_dot_output_directory_does_not_archive_its_own_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With `.` the output directory and the archive's directory coincide, so the
    archive sits on the tree being walked.

    Rendered TWICE on purpose: the first run lists its members before creating
    the archive file, so it cannot see it and passes either way. Only the second
    run walks a tree that already contains an archive — which is when a missing
    exclusion makes the archive contain the previous one, growing on every
    re-run."""
    doc = _doc_with_an_image(tmp_path / "docs")
    here = tmp_path / "here"
    here.mkdir()
    monkeypatch.chdir(here)
    assert renderer.main(["render_doc_html.py", str(doc), ".", "-z"]) == 0
    assert renderer.main(["render_doc_html.py", str(doc), ".", "-z"]) == 0

    archive = here / "guide.tar.gz"
    assert archive.is_file()
    with tarfile.open(archive) as opened:
        assert sorted(opened.getnames()) == ["guide.html", "shot.png"]


def test_the_tarball_is_byte_reproducible(tmp_path: Path) -> None:
    """`tarfile.open(..., "w:gz")` stamps the current time and the archive's own
    name into the gzip header, so two archives of one unchanged directory differ
    unless the wrapper is built by hand."""
    doc = _doc_with_an_image(tmp_path / "docs")
    out = tmp_path / "output"
    archive = tmp_path / "guide.tar.gz"

    renderer.main(["render_doc_html.py", str(doc), str(out), "-z"])
    first = archive.read_bytes()
    archive.unlink()
    renderer.main(["render_doc_html.py", str(doc), str(out), "-z"])
    assert archive.read_bytes() == first

    # The comparison above cannot see a clock-derived header: both archives are
    # written in the same second. So the header is pinned directly. RFC 1952:
    # byte 3 is FLG (bit 3, 0x08, means an original filename follows) and bytes
    # 4-7 are MTIME, little-endian.
    assert first[3] & 0x08 == 0, "the gzip header carries the archive's own filename"
    assert int.from_bytes(first[4:8], "little") == 0, "the gzip header carries a build timestamp"


def test_no_tarball_without_the_flag(tmp_path: Path) -> None:
    doc = _doc_with_an_image(tmp_path / "docs")
    renderer.main(["render_doc_html.py", str(doc), str(tmp_path / "output")])
    assert not list(tmp_path.glob("*.tar.gz"))


# ---------------------------------------------------------------------------
# Argument handling
# ---------------------------------------------------------------------------


def test_a_missing_source_is_a_usage_error(tmp_path: Path) -> None:
    assert renderer.main(["render_doc_html.py", str(tmp_path / "nope.md"), str(tmp_path / "o")]) == 2


def test_an_output_path_that_is_a_file_is_a_usage_error(tmp_path: Path) -> None:
    """Guards the old interface's muscle memory: passing `out.html` where a
    directory is expected must say so, not clobber it."""
    doc = _doc_with_an_image(tmp_path / "docs")
    existing = tmp_path / "out.html"
    existing.write_text("keep me", encoding="utf-8")
    assert renderer.main(["render_doc_html.py", str(doc), str(existing)]) == 2
    assert existing.read_text(encoding="utf-8") == "keep me"


def test_a_table_scrolls_rather_than_widening_the_page() -> None:
    """A wide table in a fixed measure must not make the whole page scroll
    sideways on a phone."""
    assert '<div class="table-scroll">' in render("# T\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n")


def test_the_page_is_self_contained_apart_from_the_brand_webfonts() -> None:
    """The consumer ships this into an OFFLINE installer: a stylesheet or script
    fetched at open time would render unstyled on the machine that matters. The
    webfonts are the one deliberate exception — they degrade to a system stack.
    """
    page = render("# T\n\nBody.\n")
    assert "<link" not in page
    assert 'src="http' not in page
    remote = re.findall(r"https?://[^\s\"')]+", page)
    assert remote, "the brand webfont declarations disappeared"
    assert all("website-files.com" in url for url in remote), (
        f"the page fetches something other than the brand fonts: {sorted(set(remote))}"
    )
