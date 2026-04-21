from tools.briefs.renderer import build_jinja_env, render_html
from tools.briefs.data.board import load_board_data


def test_board_template_renders():
    env = build_jinja_env()
    tpl = env.get_template("board.html.j2")
    data = load_board_data("2026Q2")
    out = render_html(tpl, data)
    assert 'AeroGrid · Board Report · Q2 2026' in out
    assert 'Q2 2026 saw elevated' in out
    assert 'Two items warrant board action' in out
    assert 'class="pill pill--high"' in out
    assert out.count('class="page') >= 9


def test_board_template_anchors_every_takeaway():
    env = build_jinja_env()
    tpl = env.get_template("board.html.j2")
    data = load_board_data("2026Q2")
    out = render_html(tpl, data)
    for t in data.board_takeaways:
        assert t.anchor in out
