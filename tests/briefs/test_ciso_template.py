from tools.briefs.renderer import build_jinja_env, render_html
from tools.briefs.data.ciso import load_ciso_data


def test_ciso_template_renders():
    env = build_jinja_env()
    tpl = env.get_template("ciso.html.j2")
    data = load_ciso_data("2026-04")
    out = render_html(tpl, data)
    assert 'AeroGrid · CISO Brief · April 2026' in out
    assert 'geopolitical' in out.lower()
    assert 'SolarGlare' in out
    assert 'APT28' in out
    assert out.count('class="page') >= 7


def test_ciso_template_includes_all_regions():
    env = build_jinja_env()
    tpl = env.get_template("ciso.html.j2")
    data = load_ciso_data("2026-04")
    out = render_html(tpl, data)
    for r in ("MED", "NCE", "APAC", "LATAM", "AME"):
        assert f'>{r}<' in out
