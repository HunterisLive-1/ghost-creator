"""User guide and documentation routes."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import markdown
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from config import APP_VERSION

router = APIRouter(tags=["docs"])

_INDEX_CACHE: dict | None = None


def _project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[2]


def _docs_dir() -> Path:
    return _project_root() / "docs"


def _templates_dir() -> Path:
    return _project_root() / "api" / "templates"


def _load_index() -> dict:
    global _INDEX_CACHE
    if _INDEX_CACHE is not None:
        return _INDEX_CACHE
    index_path = _docs_dir() / "index.json"
    if not index_path.is_file():
        raise HTTPException(status_code=500, detail="Documentation index missing")
    _INDEX_CACHE = json.loads(index_path.read_text(encoding="utf-8"))
    return _INDEX_CACHE


def _section_by_slug(slug: str) -> dict:
    index = _load_index()
    for section in index.get("sections", []):
        if section.get("slug") == slug:
            return section
    raise HTTPException(status_code=404, detail=f"Unknown section: {slug}")


def _read_section_markdown(section: dict) -> str:
    filename = section.get("file", "")
    if not filename or ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=500, detail="Invalid section file")
    md_path = _docs_dir() / filename
    if not md_path.is_file():
        raise HTTPException(status_code=404, detail=f"Section file missing: {filename}")
    return md_path.read_text(encoding="utf-8")


def _render_markdown(text: str) -> str:
    return markdown.markdown(
        text,
        extensions=["tables", "fenced_code", "nl2br", "sane_lists"],
    )


def _build_sidebar(active_slug: str) -> str:
    index = _load_index()
    items: list[str] = []
    for section in sorted(index.get("sections", []), key=lambda s: s.get("order", 0)):
        slug = section.get("slug", "")
        title = section.get("title", slug)
        cls = "active" if slug == active_slug else ""
        items.append(f'<a class="nav-link {cls}" href="/guide/{slug}">{title}</a>')
    return "\n".join(items)


def _render_guide_page(active_slug: str) -> str:
    section = _section_by_slug(active_slug)
    md_text = _read_section_markdown(section)
    content_html = _render_markdown(md_text)
    sidebar = _build_sidebar(active_slug)
    template_path = _templates_dir() / "guide.html"
    if not template_path.is_file():
        raise HTTPException(status_code=500, detail="Guide template missing")
    template = template_path.read_text(encoding="utf-8")
    return (
        template.replace("{{VERSION}}", APP_VERSION)
        .replace("{{TITLE}}", section.get("title", "Guide"))
        .replace("{{SIDEBAR}}", sidebar)
        .replace("{{CONTENT}}", content_html)
    )


@router.get("/api/docs")
def docs_index() -> dict:
    index = _load_index()
    sections = [
        {
            "slug": s.get("slug"),
            "title": s.get("title"),
            "order": s.get("order"),
        }
        for s in sorted(index.get("sections", []), key=lambda x: x.get("order", 0))
    ]
    return {
        "version": APP_VERSION,
        "sections": sections,
        "links": {
            "guide": "/guide",
            "api_swagger": "/docs",
            "health": "/health",
        },
    }


@router.get("/api/docs/{slug}")
def docs_section_json(slug: str) -> dict:
    section = _section_by_slug(slug)
    md_text = _read_section_markdown(section)
    return {
        "slug": slug,
        "title": section.get("title", slug),
        "order": section.get("order"),
        "markdown": md_text,
        "html": _render_markdown(md_text),
    }


@router.get("/guide", response_class=HTMLResponse)
def guide_home() -> HTMLResponse:
    index = _load_index()
    sections = sorted(index.get("sections", []), key=lambda s: s.get("order", 0))
    if not sections:
        raise HTTPException(status_code=500, detail="No documentation sections")
    first_slug = sections[0].get("slug", "overview")
    return HTMLResponse(_render_guide_page(first_slug))


@router.get("/guide/{slug}", response_class=HTMLResponse)
def guide_section(slug: str) -> HTMLResponse:
    return HTMLResponse(_render_guide_page(slug))
