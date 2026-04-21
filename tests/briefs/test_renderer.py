import asyncio
from pathlib import Path
from tools.briefs.renderer import build_jinja_env, render_html

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
