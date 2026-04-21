from jinja2 import Environment, FileSystemLoader, select_autoescape
from tools.briefs.data._rsm_mock import rsm_med_w17_mock

TEMPLATE_DIR = "tools/briefs/templates"


def _env():
    return Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html"]),
    )


def test_rsm_template_renders():
    data = rsm_med_w17_mock()
    env = _env()
    tmpl = env.get_template("rsm.html.j2")
    html = tmpl.render(data=data)
    assert "AEROGRID" in html
    assert "MED" in html


def test_rsm_template_includes_crown_jewel_site():
    data = rsm_med_w17_mock()
    env = _env()
    html = env.get_template("rsm.html.j2").render(data=data)
    # Cape Wind is the crown-jewel site in the mock
    assert "Cape Wind" in html
