# tests/test_config_api.py
import json
import pytest
import server
from fastapi.testclient import TestClient

# client is built once at collection time — that's fine; BASE is patched per-test
client = TestClient(server.app)


@pytest.fixture(autouse=True)
def tmp_data(tmp_path, monkeypatch):
    """Redirect server.BASE to an isolated temp directory for each test."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    agents_dir = tmp_path / ".claude" / "agents"
    agents_dir.mkdir(parents=True)

    topics = [{"id": "test-topic", "type": "event", "keywords": ["foo"], "regions": ["APAC"], "active": True}]
    (data_dir / "osint_topics.json").write_text(json.dumps(topics), encoding="utf-8")

    sources = [{"channel_id": "UCtest", "name": "Test Channel", "region_focus": ["AME"], "topics": ["test-topic"]}]
    (data_dir / "youtube_sources.json").write_text(json.dumps(sources), encoding="utf-8")

    agent_md = "---\nname: test-agent\nmodel: claude-haiku-4-5-20251001\ntools: []\n---\nYou are a test agent."
    (agents_dir / "test-agent.md").write_text(agent_md, encoding="utf-8")

    # Patch BASE on the module — endpoints must use BASE inline (not module-level _DATA/_AGENTS constants)
    monkeypatch.setattr(server, "BASE", tmp_path)
    yield tmp_path


def test_get_topics_returns_list():
    r = client.get("/api/config/topics")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert data[0]["id"] == "test-topic"


def test_post_topics_writes_file(tmp_data):
    new_topics = [{"id": "new-topic", "type": "trend", "keywords": ["bar"], "regions": ["MED"], "active": False}]
    r = client.post("/api/config/topics", json={"topics": new_topics})
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    saved = json.loads((tmp_data / "data" / "osint_topics.json").read_text())
    assert saved[0]["id"] == "new-topic"


def test_get_sources_returns_list():
    r = client.get("/api/config/sources")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert data[0]["channel_id"] == "UCtest"


def test_post_sources_writes_file(tmp_data):
    new_sources = [{"channel_id": "UCnew", "name": "New", "region_focus": ["NCE"], "topics": []}]
    r = client.post("/api/config/sources", json={"sources": new_sources})
    assert r.status_code == 200
    saved = json.loads((tmp_data / "data" / "youtube_sources.json").read_text())
    assert saved[0]["channel_id"] == "UCnew"


def test_get_sources_empty_when_file_missing(tmp_data, monkeypatch):
    (tmp_data / "data" / "youtube_sources.json").unlink(missing_ok=True)
    r = client.get("/api/config/sources")
    assert r.status_code == 200
    assert r.json() == []


def test_get_prompts_returns_agent_list():
    r = client.get("/api/config/prompts")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert data[0]["agent"] == "test-agent"
    assert "frontmatter" in data[0]
    assert "body" in data[0]
    assert data[0]["body"].strip() == "You are a test agent."


def test_post_prompts_preserves_frontmatter(tmp_data):
    r = client.post("/api/config/prompts/test-agent", json={"body": "New instructions."})
    assert r.status_code == 200
    content = (tmp_data / ".claude" / "agents" / "test-agent.md").read_text()
    assert "name: test-agent" in content
    assert "New instructions." in content


def test_post_prompts_unknown_agent_returns_400():
    # FastAPI rejects path-traversal at router level (404) or our allowlist check (400)
    # Either response means the request is blocked — both are acceptable
    r = client.post("/api/config/prompts/evil/../etc/passwd", json={"body": "x"})
    assert r.status_code in (400, 404)
    # Also verify a plain unknown agent name returns 400 from our allowlist check
    r2 = client.post("/api/config/prompts/nonexistent-agent", json={"body": "x"})
    assert r2.status_code == 400


def test_post_topics_atomic_write(tmp_data, monkeypatch):
    """Verify .tmp file is not left behind after successful write."""
    new_topics = [{"id": "atomic", "type": "event", "keywords": [], "regions": [], "active": True}]
    client.post("/api/config/topics", json={"topics": new_topics})
    tmp_files = list((tmp_data / "data").glob("*.tmp"))
    assert tmp_files == [], f"Temp files left behind: {tmp_files}"
