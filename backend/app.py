"""
Frontend bridge API — the ONE connection layer between the backend and the UI.

Read-only over the curated knowledge base; everything it writes is additive: run
logs under logs/frontend_runs/, graph checkpoints under logs/, auth records under
knowledge_base/auth/, and Build-Profile entries in
knowledge_base/profile/manual_entries.json plus their vectors in the `profile`
collection. Existing KB files and fixtures are never touched.

Endpoints
---------
  GET  /api/health                        liveness + mode          (OPEN)
  GET  /api/config                        secret-free config summary
  POST /api/auth/request-access           queue a signup request    (OPEN)
  POST /api/auth/request-more             queue a top-up on the caller's OWN account
  POST /api/auth/login                    exchange a token for an identity (OPEN)
  GET  /api/auth/me                       the caller's identity (now carries profile_id)
  GET  /api/auth/requests                 the request queue          (admin)
  POST /api/auth/requests/{id}/approve    approve + issue a token    (admin)
  POST /api/auth/requests/{id}/reject     reject a request           (admin)
  GET  /api/kb                            store -> files -> record counts
  GET  /api/kb/{store}/{file}             records of one KB file
  POST /api/search                        evidence retrieval over Chroma
  POST /api/runs                          start a run (spends one allowance)
  GET  /api/runs                          past runs (owner-filtered)
  GET  /api/runs/{id}/events              SSE event stream (?token=)
  POST /api/runs/{id}/gate                answer the waiting human gate
  GET  /api/runs/{id}/log                 one run's saved event trail
  GET  /api/profile/entries               Build-Profile entries
  POST /api/profile/entries               add an entry
  PUT  /api/profile/entries/{id}          edit an entry in place
  GET  /api/profile/cv                    the caller's current CV, or null
  POST /api/profile/cv                    upload a CV PDF (pending, not yet current)
  POST /api/profile/cv/{id}/confirm       make an uploaded CV current
  DELETE /api/profile/cv/{id}             remove a pending upload / unused CV
  GET  /api/me/export                     everything this account owns, as a zip
  GET  /api/logs/mine                     the caller's own audit log, projected
  GET  /api/admin/logs                    the full log plane                (admin)
  GET  /api/admin/users/{profile_id}/profile  one account's Build-Profile entries, audited (admin)
  GET  /api/admin/users/{profile_id}/cv       one account's current CV, audited        (admin)

Every route except /api/health requires `Authorization: Bearer <token>`.

Run:  .venv/bin/python -m uvicorn scripts.frontend_api:app --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.middleware.cors import CORSMiddleware

import config
from backend import logplane
from backend.auth import store
from backend.routes import admin, auth, cv, kb, logs, me, profile, runs, system

log = logging.getLogger("backend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Make sure the two data dirs exist, and refuse to be quietly unusable."""
    config.KB_AUTH_DIR.mkdir(parents=True, exist_ok=True)
    config.RUNS_DIR.mkdir(parents=True, exist_ok=True)
    logplane.LOG_DIR.mkdir(parents=True, exist_ok=True)
    if not config.ADMIN_TOKEN:
        # Without this nobody can approve an access request, so no user token
        # can ever be issued and the app is unusable. Fail loudly in the log
        # rather than silently serving a dead system.
        log.warning(
            "ADMIN_TOKEN is empty — no one can administer this bridge. "
            "Set it in .env (see .env.example) and restart."
        )
    # Both are deploy-time omissions that only show up six nodes into a run
    # (bugs_audit_fixed.md #42), so they are said once here, at boot, the same
    # way an empty ADMIN_TOKEN is. Warnings, not a refusal to start: the bridge
    # still serves auth, the KB and saved runs without either of them, and a
    # fresh deploy is expected to build the index after the API is already up.
    if not config.CV_DEFAULT_PATH.is_file():
        log.warning(
            "No sample CV at %s — an admin with no uploaded CV cannot start a run "
            "(503). Users are unaffected; they upload their own.",
            config.CV_DEFAULT_PATH,
        )
    from backend import vectorstore

    problem = vectorstore.profile_index_problem()
    if problem is not None:
        log.warning("Profile index: %s — every run will fail at cv_link until then.", problem)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Agentic frontend bridge", lifespan=lifespan)

    # Only the dashboard's own origins — "*" would let any web page open in the
    # browser drive runs, answer gates, and write profile entries via localhost.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:5173"],  # nginx / vite dev
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(HTTPException)
    async def _audit_every_403(request: Request, exc: HTTPException):
        """Every 403 lands in the audit log automatically (backend/bugs.md
        "2026-10-09 (design)" §5: "every 403"), so a new ownership check
        anywhere in this package is covered without needing its own explicit
        log line. The response itself is unchanged — this only adds the side
        effect, then falls through to FastAPI's own default handler.

        The caller is resolved from the `Authorization` header, and failing
        that from `?token=` (bugs_audit_fixed.md #69 item 3).
        `GET /api/runs/{id}/events` authenticates by query param because
        `EventSource` cannot set headers, so a 403 there - one account
        opening another's run stream, exactly the attempt this log exists to
        record - had no header to read and was written as
        `actor: "anonymous"`, `profile_id: null`. The refused user never saw
        their own refusal in `/logs/mine`, and the admin could not attribute
        it to anyone.

        The fallback is not confined to that one route, unlike
        `deps.identity_from_query_token` itself: this is attribution, not
        authentication, so a second SSE route would be covered without a
        second fix here, and presenting a token is what identifies its holder
        either way. Only the resolved `profile_id` is written, and
        `request.url.path` deliberately excludes the query string, so the
        token itself never reaches the log plane.
        """
        if exc.status_code == 403:
            raw = request.headers.get("authorization") or ""
            _, _, header_token = raw.partition(" ")
            raw_token = header_token.strip() or (request.query_params.get("token") or "").strip()
            try:
                record = store.resolve_token(raw_token) if raw_token else None
            except Exception:
                # Attribution must never turn a 403 into a 500: a damaged
                # tokens.json would otherwise answer an ordinary ownership
                # refusal with the wrong status.
                log.exception("could not attribute a 403 on %s", request.url.path)
                record = None
            identity = store.identity_of(record) if record else None
            logplane.write(
                "audit", event="forbidden",
                actor=("account" if identity else "anonymous"),
                profile_id=(identity["profile_id"] if identity else None),
                fields={"path": request.url.path},
            )
        return await http_exception_handler(request, exc)

    for router in (system.router, auth.router, kb.router, runs.router, profile.router, cv.router, logs.router,
                   me.router, admin.router):
        app.include_router(router, prefix="/api")

    return app


app = create_app()
