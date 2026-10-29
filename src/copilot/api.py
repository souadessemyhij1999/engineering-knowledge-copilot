"""FastAPI backend + static web UI.

    uvicorn copilot.api:app --reload
"""
from __future__ import annotations

import logging
import os
import shutil
import tempfile
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .access import User
from .config import load_settings, resolve
from .pipeline import Copilot

log = logging.getLogger("copilot.api")
WEB = Path(__file__).parent / "web"
oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/token")


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    mode: str | None = Field(default=None, pattern="^(extractive|llm)$")
    top_k: int | None = Field(default=None, ge=1, le=10)


class SearchRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=20)
    mode: str = Field(default="hybrid", pattern="^(dense|sparse|hybrid)$")
    rerank: bool = True


class FeedbackRequest(BaseModel):
    query_id: int
    helpful: bool
    comment: str = Field(default="", max_length=2000)


def create_app(settings: dict | None = None) -> FastAPI:
    cfg = settings or load_settings()
    state: dict = {}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        cp = Copilot(cfg)
        if cfg["app"].get("auto_ingest", True) and cp.store.count() == 0:
            res = cp.ingestor.ingest_dir(resolve(cfg["app"]["corpus_dir"]))
            log.info("auto-ingested %d documents", len(res))
        state["cp"] = cp
        yield
        state.clear()

    app = FastAPI(title="Engineering Knowledge Copilot", version=__version__, lifespan=lifespan)
    secret = os.environ.get("COPILOT_JWT_SECRET", cfg["auth"]["jwt_secret"])

    def copilot() -> Copilot:
        return state["cp"]

    def current_user(token: str = Depends(oauth2), cp: Copilot = Depends(copilot)) -> User:
        user = cp.policy.user_from_token(token, secret)
        if user is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired token",
                                headers={"WWW-Authenticate": "Bearer"})
        return user

    def admin(user: User = Depends(current_user), cp: Copilot = Depends(copilot)) -> User:
        if user.role not in cp.policy.superuser_roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "admin only")
        return user

    @app.get("/health")
    def health(cp: Copilot = Depends(copilot)):
        return {"status": "ok", "version": __version__, "chunks": cp.store.count(),
                "embedding_model": cp.embedder.name, "llm_configured": bool(os.environ.get("ANTHROPIC_API_KEY")),
                "default_mode": cp.cfg["answer"]["mode"]}

    @app.post("/auth/token")
    def login(form: OAuth2PasswordRequestForm = Depends(), cp: Copilot = Depends(copilot)):
        user = cp.policy.authenticate(form.username, form.password)
        if user is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wrong username or password")
        return {"access_token": cp.policy.issue_token(user, secret, cfg["auth"]["token_minutes"]),
                "token_type": "bearer", "user": asdict(user)}

    @app.get("/auth/me")
    def me(user: User = Depends(current_user)):
        return asdict(user)

    @app.get("/demo-users")
    def demo_users(cp: Copilot = Depends(copilot)):
        return [asdict(u) for u in cp.policy.users.values()]

    @app.post("/ask")
    def ask(req: AskRequest, user: User = Depends(current_user), cp: Copilot = Depends(copilot)):
        return asdict(cp.ask(req.question, user, mode=req.mode, top_k=req.top_k))

    @app.post("/search")
    def search(req: SearchRequest, user: User = Depends(current_user), cp: Copilot = Depends(copilot)):
        r = cp.retriever.retrieve(req.question, cp.roles_filter(user), top_k=req.top_k, mode=req.mode,
                                  rerank=req.rerank)
        return {"current_only": r.current_only, "timings": r.timings,
                "hits": [{"score": round(c.score, 4), "parts": c.parts,
                          **{k: c.payload[k] for k in ("chunk_id", "doc_no", "revision", "title", "section",
                                                       "page", "text")}} for c in r.chunks]}

    @app.get("/documents")
    def documents(user: User = Depends(current_user), cp: Copilot = Depends(copilot)):
        return cp.visible_documents(user)

    @app.post("/documents", status_code=201)
    async def upload(file: UploadFile = File(...), doc_no: str = Form(""), revision: str = Form(""),
                     title: str = Form(""), classification: str = Form(""), roles: str = Form(""),
                     user: User = Depends(admin), cp: Copilot = Depends(copilot)):
        suffix = Path(file.filename or "upload.pdf").suffix.lower()
        if suffix not in (".pdf", ".md", ".txt"):
            raise HTTPException(400, "only PDF, markdown or text files")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / Path(file.filename).name
            with path.open("wb") as fh:
                shutil.copyfileobj(file.file, fh)
            meta = {"doc_no": doc_no, "revision": revision, "title": title, "classification": classification}
            role_list = [r.strip() for r in roles.split(",") if r.strip()] or None
            unknown = set(role_list or []) - set(cp.policy.roles)
            if unknown:
                raise HTTPException(400, f"unknown roles: {sorted(unknown)}")
            res = cp.ingestor.ingest_file(path, meta={k: v for k, v in meta.items() if v}, roles=role_list)
        return asdict(res)

    @app.post("/feedback")
    def feedback(req: FeedbackRequest, user: User = Depends(current_user), cp: Copilot = Depends(copilot)):
        if not cp.db or not cp.db.add_feedback(req.query_id, req.helpful, req.comment):
            raise HTTPException(404, "unknown query id")
        return {"ok": True}

    @app.get("/stats")
    def stats(user: User = Depends(admin), cp: Copilot = Depends(copilot)):
        return cp.db.stats() if cp.db else {}

    app.mount("/static", StaticFiles(directory=WEB), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(WEB / "index.html")

    return app


app = create_app()
