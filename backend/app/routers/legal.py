"""Public legal pages served as HTML.

No authentication — these must be reachable from SFSafariViewController
on unauthenticated devices and linkable from the App Store listing.
"""
from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/legal", tags=["legal"])

_LEGAL_DIR = Path(__file__).resolve().parent.parent / "legal"

_PAGES: dict[str, tuple[str, str, str]] = {
    # slug -> (title_zh, title_en, effective_date)
    "privacy": ("隐私政策", "Privacy Policy", "Effective: April 12, 2026"),
    "terms": ("使用条款", "Terms of Use", "Effective: April 12, 2026"),
}


def _render(slug: str, lang: str) -> str:
    lang = "en" if lang == "en" else "zh"
    title_zh, title_en, effective = _PAGES[slug]
    title = title_zh if lang == "zh" else title_en

    base = (_LEGAL_DIR / "_base.html").read_text(encoding="utf-8")
    body = (_LEGAL_DIR / f"{slug}_{lang}.html").read_text(encoding="utf-8")

    return (
        base
        .replace("__TITLE__", title)
        .replace("__EFFECTIVE__", effective)
        .replace("__PATH__", f"/legal/{slug}")
        .replace("__ZH_ACTIVE__", "active" if lang == "zh" else "")
        .replace("__EN_ACTIVE__", "active" if lang == "en" else "")
        .replace("__BODY__", body)
    )


@router.get("/privacy", response_class=HTMLResponse)
async def privacy(lang: str = Query("zh")):
    return HTMLResponse(_render("privacy", lang))


@router.get("/terms", response_class=HTMLResponse)
async def terms(lang: str = Query("zh")):
    return HTMLResponse(_render("terms", lang))
