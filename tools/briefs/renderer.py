from __future__ import annotations
import asyncio
import tempfile
from pathlib import Path
from typing import Any
import jinja2

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = REPO_ROOT / "static"


def build_jinja_env() -> jinja2.Environment:
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(TEMPLATES_DIR),
        autoescape=jinja2.select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _inline_css(html: str) -> str:
    """Replace /static/design/styles/*.css link tags with inlined <style> blocks.
    Also strips screen-only .print-hint elements — never wanted in PDF output."""
    import re
    def replacer(m: re.Match) -> str:
        href = m.group(1)
        if not href.startswith("/static/"):
            return m.group(0)
        css_path = REPO_ROOT / href.lstrip("/")
        if not css_path.exists():
            return ""
        return f"<style>\n{css_path.read_text(encoding='utf-8')}\n</style>"
    html = re.sub(r'<link[^>]+rel=["\']stylesheet["\'][^>]+href=["\']([^"\']+)["\'][^>]*>', replacer, html)
    html = re.sub(r'<div[^>]+class=["\'][^"\']*print-hint[^"\']*["\'][^>]*>.*?</div>', '', html, flags=re.DOTALL)
    return html


def render_html(template: jinja2.Template, data: Any) -> str:
    return _inline_css(template.render(data=data))


async def render_pdf(
    brief: str,
    data: Any,
    out_path: Path,
    thumbnail_path: Path | None = None,
) -> None:
    from playwright.async_api import async_playwright

    env = build_jinja_env()
    template = env.get_template(f"{brief}.html.j2")
    html = render_html(template, data)

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".html",
        dir=STATIC_DIR,
        delete=False,
    ) as f:
        f.write(html)
        html_path = Path(f.name)

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(f"file://{html_path.as_posix()}")
            await page.wait_for_function("document.fonts.ready")
            await page.pdf(
                path=str(out_path),
                format="A4",
                print_background=True,
                prefer_css_page_size=True,
                margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
            )
            if thumbnail_path is not None:
                await page.locator("section.page").first.screenshot(
                    path=str(thumbnail_path),
                    scale="device",
                )
            await browser.close()
    finally:
        html_path.unlink(missing_ok=True)
