// All backend access goes through these helpers. Same-origin /api is
// proxied to the bridge (scripts/frontend_api.py) by nginx (Docker) or Vite (dev).

// Carries the HTTP status so callers can tell 401 (log back in) from 403
// (no runs left / not yours) from 404 (route not deployed). Status 0 is
// reserved for "the request never reached a server at all".
export class ApiError extends Error {
  constructor(status, text) {
    super(status === 0 ? text : `${status} ${text}`);
    this.status = status;
    // The server's own reason without the status prefix, for callers that put
    // it inside a sentence of their own.
    this.detail = text;
  }
}

// The access token, held in module scope and set once by AuthContext on boot
// and on login/logout. Every request below attaches it when present.
let token = null;
let onUnauthorized = null;

export function setToken(value) {
  token = value || null;
}

// Called on any 401 so a token revoked mid-session logs out once, centrally,
// instead of every call site having to notice. See AuthContext.
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn;
}

// These two legitimately 401 while logging in or probing on boot — firing the
// global handler there would tear down a session that was never established.
const NO_GLOBAL_401 = new Set(["/auth/login", "/auth/me"]);

// FastAPI answers an error with {"detail": "..."} — or, for a validation
// failure, {"detail": [{"msg": ..., "loc": [...]}, ...]}. Without this the raw
// body became the message and the user read
// `422 {"detail":[{"type":"string_too_long",...}]}` off the screen.
function readDetail(text) {
  try {
    const detail = JSON.parse(text)?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length) {
      const first = detail[0];
      // loc is ["body", "job_description"] — the field name is the useful half.
      const field = Array.isArray(first?.loc) ? first.loc[first.loc.length - 1] : null;
      const msg = first?.msg || "is not valid";
      return field ? `${field}: ${msg}` : msg;
    }
  } catch {
    // not JSON (an nginx page, an empty body) — fall through to the raw text
  }
  // A proxy's own HTML error page (nginx's 504 or 413) has nothing worth showing.
  return /^\s*</.test(text) ? "the server answered with an error page and no details" : text;
}

const UNREACHABLE = "cannot reach the backend";

function isJson(text) {
  try {
    JSON.parse(text);
    return true;
  } catch {
    return false;
  }
}

// The error for a non-2xx answer. A 502 that isn't FastAPI's JSON comes from the
// proxy in front of it (nginx in Docker, Caddy in production): the backend is
// down or restarting, so the request never reached it. That is the same failure
// as a refused connection, so it becomes status 0 and every caller's "can't
// reach the server" wording applies, instead of nginx's HTML page on screen.
function failure(status, text) {
  if (status === 502 && !isJson(text)) return new ApiError(0, UNREACHABLE);
  return new ApiError(status, readDetail(text));
}

async function request(method, path, body) {
  let res;
  try {
    res = await fetch(`/api${path}`, {
      method,
      headers: {
        ...(body === undefined ? {} : { "content-type": "application/json" }),
        ...(token ? { authorization: `Bearer ${token}` } : {}),
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
  } catch {
    // Network-level failure: no response, so no status. Normalise it to an
    // ApiError too, otherwise callers get a bare TypeError with no .status
    // and cannot tell "backend down" from "backend said no".
    throw new ApiError(0, UNREACHABLE);
  }
  if (!res.ok) {
    const err = failure(res.status, await res.text());
    if (res.status === 401 && onUnauthorized && !NO_GLOBAL_401.has(path.split("?")[0])) {
      onUnauthorized();
    }
    throw err;
  }
  if (res.status === 204) return null; // DELETE answers with no body
  return res.json();
}

// Upload one file as multipart form data, field `file`. XMLHttpRequest rather
// than fetch because fetch cannot report upload progress. No content-type
// header: the browser has to add the multipart boundary itself.
export function upload(path, file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `/api${path}`);
    if (token) xhr.setRequestHeader("authorization", `Bearer ${token}`);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total);
    };
    xhr.onerror = () => reject(new ApiError(0, UNREACHABLE));
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(xhr.responseText ? JSON.parse(xhr.responseText) : null);
        } catch {
          reject(new ApiError(xhr.status, "the server's reply could not be read"));
        }
        return;
      }
      if (xhr.status === 401 && onUnauthorized) onUnauthorized();
      reject(failure(xhr.status, xhr.responseText));
    };
    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
}

// Save a file the API serves. A plain <a href> cannot carry the bearer token,
// so fetch the bytes with it and hand them to the browser as a download.
export async function download(path, filename) {
  let res;
  try {
    res = await fetch(`/api${path}`, { headers: token ? { authorization: `Bearer ${token}` } : {} });
  } catch {
    throw new ApiError(0, UNREACHABLE);
  }
  if (!res.ok) {
    const err = failure(res.status, await res.text());
    if (res.status === 401 && onUnauthorized) onUnauthorized();
    throw err;
  }
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export const get = (path) => request("GET", path);
export const post = (path, body) => request("POST", path, body ?? {});
export const put = (path, body) => request("PUT", path, body ?? {});
export const del = (path) => request("DELETE", path);

// Live run events (server-sent). Returns a close() function.
// EventSource cannot set headers, so the token rides as a query param — the
// backend accepts ?token= on this route only.
export function openEvents(runId, onEvent, onEnd) {
  const query = token ? `?token=${encodeURIComponent(token)}` : "";
  const source = new EventSource(`/api/runs/${runId}/events${query}`);
  source.onmessage = (msg) => onEvent(JSON.parse(msg.data));
  source.onerror = () => {
    source.close();
    if (onEnd) onEnd();
  };
  return () => source.close();
}
