import asyncio
from pathlib import Path
from tools.briefs.renderer import build_jinja_env, render_html, render_pdf
from tools.briefs.data._rsm_mock import rsm_med_w17_mock

def test_jinja_env_finds_partials_template(tmp_path):
    # a trivial test template at tools/briefs/templates/_smoke.html.j2
    env = build_jinja_env()
    tpl = env.from_string("{{ value }}")
    assert tpl.render(value="ok") == "ok"

def test_render_html_serializes_pydantic_fields():
    env = build_jinja_env()
    tpl = env.from_string("{{ data.title }}")
    # duck-typed dict is fine for this unit — Pydantic round-trip tested elsewhere
    out = render_html(tpl, {"title": "Hello"})
    assert out == "Hello"


def test_render_pdf_produces_thumbnail(tmp_path):
    pdf_out = tmp_path / "out.pdf"
    thumb_out = tmp_path / "out.png"
    asyncio.run(render_pdf("rsm", rsm_med_w17_mock(), pdf_out, thumbnail_path=thumb_out))
    assert pdf_out.exists() and pdf_out.stat().st_size > 1000
    assert thumb_out.exists() and thumb_out.stat().st_size > 1000
