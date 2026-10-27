"""
Backend package for the frontend bridge API.

`scripts/frontend_api.py` is kept as a thin re-export shim so the documented run
command (`uvicorn scripts.frontend_api:app`) and the nginx / Vite `/api` proxies
keep working unchanged. Everything real lives here.

  app.py        FastAPI app: CORS, router registration, startup checks
  deps.py       require_auth / require_admin / SSE query-token resolver
  jsonstore.py  atomic JSON read+write (tmp file + os.replace)
  auth/store.py access requests + issued tokens (pure file I/O, no FastAPI)
  runs/         per-owner run registry + the graph worker thread
  routes/       one router per domain (system, auth, kb, runs, profile)
"""
