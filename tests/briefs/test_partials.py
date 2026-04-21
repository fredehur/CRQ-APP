from tools.briefs.renderer import build_jinja_env

def test_pill_macro_renders_severity_class():
    env = build_jinja_env()
    env.loader.searchpath.append(str(env.loader.searchpath[0]))  # idempotent
    tpl = env.from_string(
        '{% import "_partials.html.j2" as p %}{{ p.pill("Critical", "critical") }}'
    )
    out = tpl.render()
    assert 'class="pill pill--critical"' in out
    assert ">Critical<" in out

def test_sev_chip_macro():
    env = build_jinja_env()
    tpl = env.from_string(
        '{% import "_partials.html.j2" as p %}{{ p.sev("HIGH", "high") }}'
    )
    assert 'class="sev sev--high"' in tpl.render()
