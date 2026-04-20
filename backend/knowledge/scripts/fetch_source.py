"""Fetch a knowledge source page with Playwright and archive it.

Usage:
    python fetch_source.py <url> --site merck --slug vomiting-in-dogs

Outputs:
    sources/<site>/<slug>.html          # raw rendered HTML
    sources/<site>/<slug>.meta.json     # url, title, accessed_at, site
    drafts/<slug>.md                    # main-text extract (for rewriting)
"""

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent  # backend/knowledge/
SOURCES = ROOT / "sources"
DRAFTS = ROOT / "drafts"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)

# Site-specific content selectors; fall back to <main>/<article>.
MAIN_SELECTORS = {
    "merck": "main article, main, article",
    "aaha": "main, article",
    "wsava": "main, article",
    "capc": "main, article",
    "vca": "main, article",
    "cornell": "main, article",
    "avma": "main, article",
    "fda": "main, article",
    "default": "main, article, body",
}


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-")[:80]


async def fetch(url: str, site: str, slug: str | None) -> dict:
    site_dir = SOURCES / site
    site_dir.mkdir(parents=True, exist_ok=True)
    DRAFTS.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=UA)
        page = await context.new_page()

        print(f"→ GET {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        try:
            await page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:
            pass

        title = (await page.title()) or "untitled"
        final_slug = slug or slugify(title)

        html = await page.content()
        selector = MAIN_SELECTORS.get(site, MAIN_SELECTORS["default"])
        main_text = ""
        try:
            main_text = await page.locator(selector).first.inner_text(timeout=5_000)
        except Exception:
            main_text = await page.locator("body").inner_text()

        await browser.close()

    html_path = site_dir / f"{final_slug}.html"
    meta_path = site_dir / f"{final_slug}.meta.json"
    draft_path = DRAFTS / f"{final_slug}.md"

    html_path.write_text(html, encoding="utf-8")
    meta = {
        "url": url,
        "site": site,
        "title": title,
        "slug": final_slug,
        "accessed_at": datetime.now(timezone.utc).isoformat(),
        "html_path": str(html_path.relative_to(ROOT)),
        "draft_path": str(draft_path.relative_to(ROOT)),
        "content_length": len(main_text),
    }
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    draft = (
        f"# {title}\n\n"
        f"> Source: {url}\n"
        f"> Accessed: {meta['accessed_at']}\n"
        f"> Site: {site}\n\n"
        f"---\n\n"
        f"{main_text.strip()}\n"
    )
    draft_path.write_text(draft, encoding="utf-8")

    print(f"✓ html   → {html_path}")
    print(f"✓ meta   → {meta_path}")
    print(f"✓ draft  → {draft_path}  ({len(main_text):,} chars)")
    return meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--site", required=True, help="merck|aaha|wsava|capc|vca|cornell|avma|fda")
    ap.add_argument("--slug", help="override slug (default: from page title)")
    args = ap.parse_args()
    try:
        asyncio.run(fetch(args.url, args.site, args.slug))
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
