import subprocess, sys
def test_build_pdf_requires_brief_flag():
    r = subprocess.run(
        [sys.executable, "-m", "tools.build_pdf"],
        capture_output=True, text=True
    )
    assert r.returncode != 0
    assert "--brief" in (r.stderr + r.stdout)

def test_build_pdf_rejects_unknown_brief():
    r = subprocess.run(
        [sys.executable, "-m", "tools.build_pdf", "--brief", "bogus"],
        capture_output=True, text=True
    )
    assert r.returncode != 0
