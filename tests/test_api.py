import pytest
from fastapi.testclient import TestClient

from conftest import make_settings
from copilot.api import create_app


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app(make_settings())) as c:
        yield c


def token(client, user):
    r = client.post("/auth/token", data={"username": user, "password": "demo"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_health_and_ui(client):
    h = client.get("/health").json()
    assert h["status"] == "ok" and h["chunks"] > 100
    assert "Engineering Knowledge Copilot" in client.get("/").text


def test_auth_required(client):
    assert client.post("/ask", json={"question": "torque?"}).status_code == 401
    assert client.post("/auth/token", data={"username": "olga.operator", "password": "x"}).status_code == 401


def test_ask_and_feedback(client):
    h = token(client, "olga.operator")
    r = client.post("/ask", json={"question": "What torque for the M10 flange bolts?"}, headers=h)
    body = r.json()
    assert r.status_code == 200 and "45 Nm" in body["answer"] and body["query_id"]
    fb = client.post("/feedback", json={"query_id": body["query_id"], "helpful": True}, headers=h)
    assert fb.status_code == 200


def test_validation(client):
    h = token(client, "olga.operator")
    assert client.post("/ask", json={"question": "x"}, headers=h).status_code == 422
    assert client.post("/ask", json={"question": "torque?", "mode": "magic"}, headers=h).status_code == 422


def test_documents_per_role(client):
    op = {d["doc_no"] for d in client.get("/documents", headers=token(client, "olga.operator")).json()}
    adm = {d["doc_no"] for d in client.get("/documents", headers=token(client, "ada.admin")).json()}
    assert "QR-AUD-2026-03" not in op and "QR-AUD-2026-03" in adm


def test_search_endpoint(client):
    h = token(client, "max.maintenance")
    r = client.post("/search", json={"question": "E-205", "top_k": 3}, headers=h).json()
    assert r["hits"][0]["doc_no"] == "TS-ROB-004"


def test_upload_admin_only_and_role_scoped(client):
    files = {"file": ("SHIFT-NOTE.md", b"# Night shift\n\nThe hall 2 door code changes to 4711 on Monday.\n",
                      "text/markdown")}
    form = {"doc_no": "SHIFT-NOTE-1", "revision": "A", "title": "Night shift note", "roles": "maintenance"}
    assert client.post("/documents", files=files, data=form, headers=token(client, "olga.operator")).status_code == 403
    r = client.post("/documents", files=files, data=form, headers=token(client, "ada.admin"))
    assert r.status_code == 201 and r.json()["chunks"] == 1
    q = {"question": "What is the new door code for hall 2 night shift?"}
    mt = client.post("/ask", json=q, headers=token(client, "max.maintenance")).json()
    op = client.post("/ask", json=q, headers=token(client, "olga.operator")).json()
    assert "4711" in mt["answer"]
    assert "4711" not in op["answer"]
    bad = client.post("/documents", files=files, data={**form, "roles": "janitor"}, headers=token(client, "ada.admin"))
    assert bad.status_code == 400


def test_stats_admin_only(client):
    assert client.get("/stats", headers=token(client, "quinn.quality")).status_code == 403
    assert client.get("/stats", headers=token(client, "ada.admin")).json()["queries"] >= 1
