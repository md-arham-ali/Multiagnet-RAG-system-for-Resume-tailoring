> **Note on this file (2026-08-27):** this is the **frontend visual/UX spec**, not
> a system-architecture design doc. Agent + orchestration design lives in
> `context/agent_brain_build.md` and `context/critic_verifier_design.md`; bugs in
> `context/bugs.md`. Nothing agent-side was merged into this file.
>
> Its filename previously carried a **trailing space** (`"design.md "`), which
> silently broke `@context/design.md` references and the file-reading tools.
> Renamed to `design.md` on 2026-08-27. Textual references elsewhere
> (`frontend/bugs.md`) already spelled it without the space, so nothing else
> needed changing.
>
> **One agent-side decision does affect this spec — see the addendum at the
> bottom: a fifth human gate.**
>
> **Second addendum (2026-10-09): "Your CV", the user's CV upload.** Built on both
> sides as of 2026-10-10 (frontend compiled 2026-10-10, not yet run in a
> browser); see its status note.

## Open items in this spec, by criticality (reconciled 2026-10-12)

The folder's full ranked list is at the top of `bugs.md`; these are the items
that concern this spec. The numbers in brackets are that list's.

1. ✅ **The evidence source is unlabelled** [2]. Closed by `bugs.md` Rounds 27
   and 28 (compiled 2026-10-14, not yet viewed). The start screen, the run line and the
   final review now say the evidence is a "shared sample profile, not your
   own", and no screen calls it "your profile". Remove that wording when the
   per-user profile lands.
2. 🟠 **Gate rounds, exactly** [4]. The fifth-gate addendum's assumption 2
   ("gate 4, round 1" vs "round 2") is now met by a client-side count
   (`bugs.md` Round 19). "Round N of M" and a last-redo warning need
   `revision` / `max_revisions` on the wire.
3. 🟠 **CV addendum rules the backend doesn't meet yet** [5, 7]:
   - a CV a run references must not be deleted;
   - re-uploading a stored CV must not look like a new upload;
   - a re-issued token can't see its old CV.
4. 🟡 **CV addendum wording blocked on data** [20]: "a first run will barely
   change your CV" needs the unmatched-line count.
5. ⚪ **The "presentable" backlog**: in criticality order in its status table
   at the bottom (Feature 5, admin token management, first).
6. ⚪ **The critique-review (fifth) gate**: blocked on the loop-back design.

**Built against this spec since 2026-10-10** (`bugs.md` Rounds 27–38,
compiled 2026-10-14, not yet viewed). These are deltas to the text below, not
rewrites of it:
- **The final review's changes** (Round 37):
  - grouped by CV section;
  - each line labelled "was" / "now", so colour isn't the only cue;
  - changed words highlighted;
  - the records each change cites shown on expand.

  That's the "why should I trust this line" view, while the fact check is
  still a placeholder.
- **Agent states:** the spec lists idle, running, waiting, complete and
  flagged. An ended run now also shows **stopped** (amber) and **failed** (red)
  on the step it left off at, with no pulse (Round 33).
- **"Error states are specific":** a review whose run the server lost after a
  restart says so, and its buttons retire (Round 31).
- **No modals:** leaving an unsaved CV edit by Log out or "new run" asks
  inline, like Cancel (Round 30). A run that ends mid-edit keeps the edit on
  screen with Copy (Round 32). "Reset to the draft" in the editor asks inline
  too (Round 38).
- **The CV editor** (Round 38): a Preview, a reading view of the Markdown,
  labelled as not the PDF's layout; and a character count.

---

Design a minimalist, technical frontend for an agentic AI pipeline dashboard.
Visual language: dark-mode first, monospace or semi-monospace typography, tight spacing, low visual noise. Inspired by Claude's clean chat interface — no decorative elements, no gradients, no icon overload. Every element on screen earns its place.
Aesthetic reference: terminal-meets-product. Technical without being raw. Clean without being sterile. Comparable to Linear, Vercel dashboard, or Anthropic's own UI — sparse, confident, high information density without clutter.
Core UI requirements:
Display the live execution of a multi-agent LangGraph pipeline. Each agent (JD Analysis, Profile, Matching, Critic, Document, Verifier, Evaluation, Supervisor) has a visible state — idle, running, waiting, complete, flagged. Show agent transitions and routing decisions as they happen, not after.
Show the RAG retrieval layer — when the Retrieval Agent queries the vector store, display the query, the top-k results returned, and their relevance scores. No jargon — label it "knowledge search" or "evidence retrieval" rather than "RAG pipeline."
Show the Knowledge Base as a navigable panel — profile store, documents store, do-not-claim list, learning store — with simple file/chunk browsing. No database terminology exposed to the UI.
Show the shared ApplicationState object updating in real time as agents write to it — a structured, readable side panel, not a raw JSON dump.
Human approval gates are first-class UI elements — not modal popups, but dedicated full-width review screens with clear approve / request edit / reject actions and a structured feedback input.
Show the learning store activity — when an agent reads its exemplars and when new corrections are saved after a run. Label it "agent memory" not "learning store."
Layout:
Single-page app. Left sidebar for navigation (Knowledge Base, Runs, Settings). Main panel for the active pipeline run — agent graph visualization at top, live state panel below. Right drawer for detail views (retrieved evidence, critique report, eval scores) that slide in without leaving the main view.
Tone:
No marketing language. No loading spinners with motivational copy. Status labels are functional: "retrieving," "reviewing," "waiting for input," "complete." Error states are specific, not generic.
Technical display without jargon:

"RAG" → "evidence retrieval"
"vector store" → "knowledge index"
"embeddings" → omit entirely from UI, show results only
"LLM call" → "agent thinking" or just show output directly
"StateGraph" → never shown
"tokens" → omit
"do-not-claim list" → "claim boundaries"
"learning store" → "agent memory"

Deliverables:
Design the component hierarchy, layout structure, and key screen states (idle, mid-run, human gate active, run complete). Then implement as a single-page React app with Tailwind utility classes only. No component libraries. One file per component. Keep it as close to how Claude's own interface feels — quiet, fast, purposeful.

Additional section — Knowledge Base Feeding Interface:
Include a dedicated section in the UI for populating the knowledge base through a conversational question-and-answer interface. This is the human-facing data entry layer — not a file upload form, not a raw text editor.
The interface presents one question at a time, asked by the system, answered by the user in a chat-like input. Questions are structured and sequential — covering projects, skills, achievements, education, internships, extracurriculars — but feel like a natural conversation, not a form.
Visual style: mirrors a minimal chat interface. System question on the left, user input on the right. Clean text, no bubbles, no avatars. Just the exchange.
As the user answers, show a live preview panel on the right side — the structured entry being built from their answers, displayed as it will be stored in the knowledge base. The user can see exactly what is being committed before confirming.
After each answer is confirmed, the entry is written to the correct knowledge base sub-store (profile, documents, etc.) automatically — no manual categorization by the user. The system infers the category from the question context.
Include a progress indicator — not a percentage, but a simple section tracker: "Projects → Skills → Achievements → Education → Internships → Extras." Shows where you are, what is complete, what is remaining.
Allow the user to go back and edit any previously entered answer without restarting the session. Edited entries update the knowledge base in place.
Label this section in the navigation as "Build Profile" — not "feed database," not "knowledge base ingestion," not "data entry."
The tone of the questions should be direct and specific — "What did you build in your last project?" not "Please describe your project experience." One question, one answer, one entry. No multi-part questions.

---

# Addendum (2026-08-27) — a fifth human gate is now designed

Recorded here because this spec assumes **four** gates throughout, and that is
no longer the design. Nothing above has been rewritten; this is the delta.
Full reasoning: `context/critic_verifier_design.md` §3.4,
`context/agent_brain_build.md` §4.5.

## What changes

A **critique review gate** joins the four artifact gates. It is structurally
different from all of them: the existing four ask *"is this artifact good?"* —
this one asks **"was this criticism correct?"** The user reviews the reviewer.

- Fires **after both Critic and Verifier have finished**, before any loop-back
  executes. One shared gate, not one per agent.
- The user's decision **drives routing** — the Supervisor reads it and decides
  which agent fixes what. Not advisory, not log-only.
- It can fire **more than once per run** (once per revision round), unlike the
  current four which each fire at most once.

## What the screen has to show

Not an artifact — a **list of findings against an artifact**:

- Per finding: the **specific flagged line or claim**, the rubric dimension or
  check it failed, severity, and the suggested fix
  (`Critique.items[].rubric_item / severity / location / instruction`).
- Verifier findings are a different shape and should read differently:
  unsupported/contradicted **claims** (`ClaimCheck`) and **do-not-claim hits**
  (`DoNotClaimHit`, with the matched forbidden entry). A do-not-claim hit is a
  hard violation, not a suggestion — worth visual separation from graded ones.
- A **compliance score** from the format/ATS checker module, with the specific
  misses listed.
- Per finding, the user judges whether the flag itself was right. That judgement
  is persisted to agent memory (`learning/store.save_correction`) to tune the
  Critic/Verifier over time.

## Jargon-free labels (extending this spec's own vocabulary list)

- "Critic agent" → **"review"** · "Verifier" → **"fact check"**
- `Critique.items` → **"findings"** · `DoNotClaimHit` → **"claim boundary hit"**
  (this spec already maps "do-not-claim list" → "claim boundaries")
- "grounding / unsupported claim" → **"not backed by your profile"**
- Do not surface `revision_count`, `Stage`, or `SupervisorDecision`.

## Two existing assumptions this breaks

1. **"Four gates" is stated or implied in several places** — this spec, plus
   `backend/context.md` and `frontend/context.md`. The gate list is no longer
   fixed at four.
2. **A gate answered once stays answered** — the current UI can assume a gate is
   done for the run once submitted. With revision rounds, gates 3, 4 and this new
   one can reopen with *new* content under the same name. The UI needs to
   distinguish "gate 4, round 1" from "gate 4, round 2" or it will look like a
   duplicate. (This is the frontend-visible half of `context/bugs.md` #11.)

**Not buildable yet** — blocked on the loop-back redesign (bugs #10/#11 +
audit #1/#2). Recorded now so the UI work is not designed twice.

---

# Addendum (2026-10-09): "Your CV", where a user supplies the CV a run tailors

> **Status 2026-10-10: built on both sides.**
> - **Frontend:** the strip, "What we read", the Account row and the run header
>   (`bugs.md` Round 12; Round 20 guards the current CV). Compiled 2026-10-10;
>   not yet run in a browser.
> - **Backend:** the four routes, storage, and resolving the CV at run start
>   (`backend/bugs.md` → 2026-10-10).
> - **Not met yet:** keeping files that runs reference, a clear answer when a
>   stored CV is re-uploaded, the unmatched count, and per-line CV text in
>   events. See the ranked list at the top of this file.
>
> The original note follows, as written.
>
> **Status: design only. Nothing below is built.** Written from the Backend role
> after checking the tree on 2026-10-09:
> - There is no upload route.
> - There is no file picker.
> - `POST /api/runs` takes only `{job_description, mode, pace_seconds}`.
> - `backend/runs/worker.py:216-221` passes `config.CV_DEFAULT_PATH` (the sample
>   `knowledge_base/input/CV_test.pdf`) to every run.
>
> Like the fifth-gate addendum, this is a delta. Nothing above is rewritten.

## Why this is needed now

- Since 2026-10-06, Document **patches an existing PDF CV**. It no longer writes
  one from scratch.
  - `cv_link` raises without `state.cv_path`.
  - So a CV is now a **required input** to every run, as required as the job
    description.
- Today every browser run tailors the same sample CV, and the Pipeline screen
  doesn't say so.
- Stage 0's exit check "downloads a … CV built from their own profile" can't be
  met until a user can supply their own.

## How this fits with the rest of the spec

- **"Build Profile" stays a conversation, not a file upload** (line 46 above, and
  that still holds). The CV is not knowledge-base data. It is the **document
  being edited**, so it gets its own small surface instead of turning Build
  Profile into an upload form.
- **Uploading a CV does not write anything into the profile.**
  - Pulling records *out of* a CV into the profile is "Idea B" in
    `context/context_Agents+Orchestration.md`.
  - It has to go through the same propose → confirm → commit path as the intake
    gate.
  - It is out of scope here. See "Later" at the bottom.

## Where it lives in the UI

1. **On the Pipeline start screen, above the job-description box: a one-line CV
   strip.** It is always visible before a run starts.
   - With a CV: `CV  ·  ali_cv_2026.pdf  ·  2 pages  ·  uploaded 9 Oct    [Replace]`
   - Without one: `CV  ·  none yet    [Upload PDF]`, and **Start run is
     disabled**, with the reason shown inline: "Add your CV to start a run".
   - Sample fallback, only if decision D-CV2 below allows it:
     `CV  ·  sample CV (not yours)    [Upload PDF]`. The label stays in muted
     warning colour for the whole run.
2. **In Account: a "Your CV" row**, with the same details plus **Replace** and
   **Delete**. Delete asks for confirmation inline. It never opens a modal (the
   spec's no-modal rule).
3. **During and after a run: which CV it used**, shown in three places:
   - the run header;
   - the gate 3 and gate 4 review screens ("tailoring: ali_cv_2026.pdf");
   - `FinalOutput` ("tailored from ali_cv_2026.pdf, uploaded 9 Oct").

   Runs list and Run log rows show the file name too, so an old run stays
   readable after the CV is replaced.

## The upload flow and its screen states

The upload is a **file picker plus drag-and-drop on the strip itself**. It has no
separate page or wizard. These are its states, with labels in the spec's
functional tone:

| State | What the strip shows |
|---|---|
| idle, no CV | `none yet` · **Upload PDF** |
| client-side reject | specific reason: "Not a PDF" / "Larger than 5 MB". Nothing is sent |
| uploading | `uploading…` with a thin progress bar (bytes, not a spinner) |
| reading | `reading your CV` while the server parses it. Parsing has no model load, so it should take about a second |
| read preview | **What we read**, an inline expandable panel (described below). Buttons: **Use this CV** / **Cancel** |
| ready | the one-line strip from above |
| failed | a specific server reason (see the error table). The previous CV, if any, is kept and shown |

**The "What we read" preview** is the one piece of real design here.
- The parser (`utils/cv_handling/cv_extract.parse_cv`) is deterministic.
- When it mis-reads a CV, every later step patches the wrong structure, and the
  user would only find out at gate 4.
- So show the parse **before** the CV is accepted:
  - the sections found, in order, each with an entry count and a line count
    ("Projects · 3 entries · 9 lines"), collapsed by default;
  - expanding a section shows its entries and lines as plain text, read-only.
    This is the same display as `RecordCard`, not a JSON tree;
  - **warnings** from the parser, in plain words: "No Skills section found",
    "3 lines could not be placed in a section";
  - two actions: **Use this CV** (makes it current) and **Cancel** (throws the
    upload away).
- Inline editing of what was read is **not** in scope. If the read is wrong, the
  user fixes the PDF and uploads it again.

**Replacing a CV** goes through the same flow. The old CV stays current until the
new one is confirmed with **Use this CV**. A run already in progress keeps the CV
it started with.

## Error states (specific, never generic)

| Server status | Meaning | UI text |
|---|---|---|
| 413 | over the size cap | "This PDF is larger than 5 MB." |
| 415 | not a PDF (fails the `%PDF-` magic-byte check, whatever the extension says) | "This file isn't a PDF." |
| 422 `no_text` | a scanned or image-only PDF, so no text layer | "This PDF has no selectable text. It looks scanned. Export it from your editor as a text PDF." |
| 422 `no_sections` | text was read but no known section heading matched | "We couldn't find CV sections (Experience, Projects, Skills…) in this PDF." |
| 422 `too_many_pages` | over the page cap | "Keep your CV to 4 pages or fewer." |
| 409 on `POST /runs` | the caller has no current CV | Start run stays disabled. Shown only if a stale screen got past the guard |
| 403 | not your CV | the generic 403 handling. **Never 401**, per the status-code discipline, or the user gets logged out |

## What the backend has to provide (the contract this screen needs)

All routes are guarded by `require_auth` and scoped to the caller. No route ever
takes a path from the client.

| Route | Request | Response |
|---|---|---|
| `POST /api/profile/cv` | `multipart/form-data`, one field `file` | `201 {cv: CvSummary, preview: CvPreview}`. Stored as **pending**, not yet current |
| `POST /api/profile/cv/{cv_id}/confirm` | — | `200 {cv: CvSummary}`. Makes it current |
| `DELETE /api/profile/cv/{cv_id}` | — | `204`. Pending uploads, and CVs no run references, are removed from disk |
| `GET /api/profile/cv` | — | `{cv: CvSummary \| null}`, the current CV |
| `POST /api/runs` | unchanged body | the server resolves the caller's **current** CV. `409` if there is none, checked **before** `consume_run` so no allowance is spent |
| run events / run log | — | `run_started` (or the run record) carries `cv: {id, filename}`. **Never** the CV text |

- `CvSummary = {id, filename, size_bytes, pages, uploaded_at}`.
- `CvPreview = {sections: [{type, title, entries: [{header, lines: [str]}]}],
  warnings: [str]}`. It is built from `parse_cv`'s `CVTree`.

**Backend rules this design depends on:**
- **Storage.** The file is saved under a **server-chosen name**,
  `uploads/{owner}/cv/{sha256[:12]}.pdf`, never the uploaded filename. The
  original filename is kept only as display metadata.
  - `owner` is `profile_id` once §13.1 lands. Until then it is `token_id`, with
    the known caveat that a re-issued token can't see its old CV.
  - The folder is git-ignored and on the persisted volume.
- **Caps.**
  - 5 MB and 4 pages.
  - The upload is read in chunks with the cap enforced, never loaded whole and
    then checked.
  - Parsing runs on a worker thread, not on the event loop.
- **A run keeps its CV.**
  - The worker passes the resolved, server-side path as `cv_path`, replacing
    `config.CV_DEFAULT_PATH` at `worker.py:221`.
  - A CV referenced by a run log is not deleted while that log exists. Deleting
    the current CV only clears the pointer.
- **Privacy.** A CV holds contact details.
  - The CV text never goes into SSE events, run logs or URLs.
  - Only `{id, filename}` travels.
  - `gate_done` must not echo CV text, the same rule as `pasted_text` in
    `backend/context.md` October §2.
- **Dependencies to add.**
  - `python-multipart` is installed in `.venv` (0.0.32) but is **not** in
    `requirements.txt`. FastAPI file uploads need it.
  - nginx's default `client_max_body_size` is **1 MB**, and `frontend/nginx.conf`
    doesn't set it. Uploads between 1 and 5 MB would fail at the proxy with a 413
    nginx error page, not the API's JSON. Set it to `6m` on `location /api/`.

**What the frontend has to change beyond the new components:**
- `api.js`'s `request()` always sends a JSON content-type and body. It needs an
  `upload(path, file)` sibling that sends `FormData`.
  - It must **not** set `content-type`; the browser adds the multipart boundary.
  - It keeps the `authorization` header and the same 401/`ApiError` handling.
- ~~`stubs.js` needs a stub `CvSummary` and `CvPreview`, so the screens can be
  built before the backend lands.~~ Decided against (`bugs.md` Round 12): it would
  put a fabricated CV on screen, the lesson that got `stubs.js` deleted on
  2026-09-24. The screens were built against the real contract instead.

## Out-of-lane dependencies (not Frontend or Backend)

- **The CV is linked against the shared synthetic `profile` collection.**
  - `cv_link` links lines against the **global** collection
    (`agents/CV_Link.py`, `Matcher(*_get_parts())`).
  - So a real user's CV would be linked to the synthetic records, not their own.
  - Linking scoped to the user's profile is §13.3/§13.5 work (KB+RAG lane), and
    has to land before a user's CV is meaningfully linked.
- **A new user with an empty profile.** Every CV line comes back unmatched, so
  Document has no evidence to edit with. Until the intake gate (Stage 0 §4)
  fills the profile, a first run will mostly return the CV unchanged. The UI
  should say so at gate 4 rather than look broken. That wording is a Frontend
  task once the backend exposes the unmatched count.
- **`cv_link`'s skip-if-already-linked check keys on `source_file == pdf.name`.**
  With server-chosen names `{sha}.pdf` this stays correct: a different upload
  means a different name. It would break if files were stored under the user's
  own filename. That is one more reason for the storage rule above.

## Open decisions (recommendation first)

| # | Decision | Recommendation |
|---|---|---|
| D-CV1 | Is CV upload in Stage 0? The Stage 0 plan lists "PDF CV upload" as **deferred**, while Document now needs a CV | **Yes, in Stage 0.** Without it, exit criterion 1 can't be met. Move it out of the deferred list |
| D-CV2 | No CV: block the run, or fall back to the sample CV | **Block** for users, and allow the sample for the admin/demo profile only, clearly labelled |
| D-CV3 | Keep old CV versions | Keep every file a run references, plus one "current" pointer. No version-history UI in Stage 0 |
| D-CV4 | Should the paste box at the intake gate (`pasted_text`) ever become the CV source? | **No.** Pasted text has no layout to patch. It feeds the profile; the PDF is what gets edited |

> **2026-10-10:** D-CV1 and D-CV2 were taken as recommended and are built. D-CV3
> is half built: the backend deletes a file even if a run references it
> (`bugs.md` top, item 5). D-CV4 is unchanged.

## Later (not this feature)

- **Idea B:** pull records out of the uploaded CV into the profile, through the
  intake confirm gate.
- A side-by-side "your CV ↔ tailored CV" diff at gate 4.
- DOCX upload.

---

# Addendum (2026-08, logged 2026-10-10) — the "make it presentable" backlog, and what it was filtered against

> Design discussion, recorded because the **reasoning** behind the list matters
> more than the list. The items themselves live in `bugs.md` → Features 3–16
> (written at the time, numbered to follow Features 1–2, the auth system and the
> gate-4 artifact fix). Several have since been built; the status table below is
> the reconciliation. Nothing here is a new requirement.

## Where the list came from

The user pasted a full spec for **an unrelated monitoring dashboard** — a public
stats dashboard, an admin console, an access page, with model leaderboards, risk
charts, backtests and tiered data-quality checks — and asked which parts fit
this project. So this addendum is a filtering exercise, not a design brief, and
the filter is the thing worth keeping.

## What was taken, and why it survived the filter

Each of these maps onto something this app *already has or already computes* —
that was the test. No item was accepted because it would look impressive.

| Idea | Why it fit |
|---|---|
| Lazy panels | Every view mounts at once here, so hidden views were fetching on boot. The reference spec's "4 requests, everything else on open" is the same problem. |
| Vertical pipeline stepper with a nested "technical detail" layer | `design.md`'s own jargon-free rule (above) is only half-followed; a per-step plain-language "what/why" with the raw artifact behind a disclosure is exactly that rule, and `renderArtifact` already is the detail layer. |
| Admin token management (revoke, grant extra runs) | The admin side could issue tokens but never see or change one afterwards. |
| Identity as a dropdown | A static badge plus a separate logout link, where the reference spec had one menu. |
| A design-tokens file | Every colour is an inline hex literal with no theme layer (see `context.md` → Styling). Consistent today only because one person wrote it in one sitting. |
| Defensive mounting | One render throw blanked the whole app. The reference spec's per-section try/catch is an `ErrorBoundary` here. |
| Account page | A logged-in user had no page of their own, and an exhausted token stranded them: login checks the token *exists*, not that it has runs left. |
| Admin audit log | This project audits everything else (gate snapshots, run event logs); admin actions left no trail. |
| Logout and session edge cases | Logging out mid-run orphans the stream; a token revoked mid-session failed call-by-call with no central reaction. |
| Evidence-quality panel | Profile already computes strong/partial/none per requirement and Verifier already produces claim checks — the reference spec's pass-rate bars + one verdict sentence over data that already exists, no new endpoint. |
| Sparkline / time filter / run comparison | Deferred *on purpose*: a sparkline over stub scores would be actively misleading. Blocked until Evaluation is real. |

## What was rejected, and why — the useful half

- **"Awaiting manual execution" queue.** That system's backend never runs
  anything; a human executes a printed CLI command. This backend runs the graph
  itself. Nothing to queue.
- **"Redeem token → returns the exact CLI command, never executes it."** Same
  reason.
- **Username/password, session cookies, CSRF, lockout, "change password".**
  Superseded by this project's own decision: one opaque bearer token, no
  passwords, no hashing dependency (`context.md` → Auth). Re-open only if that
  decision changes.
- **Cache-busted asset URLs (`?v=…`).** Vite already content-hashes every built
  asset. Redundant.
- **Model leaderboard, backtest, drivers, risk bands.** Specific to that
  system's ML-comparison problem. This project has no equivalent; the score
  history and run comparison above are the nearest honest analogues.

**The pattern worth remembering:** every rejection came from a structural
difference (who executes the work, what the credential is, what the build
already does), not from taste. When the next reference spec arrives, filter it
the same way — against what this system actually is and already computes.

## Status, reconciled 2026-10-12 — open items first, by criticality

| # | Idea | Status | Why this rank |
|---|---|---|---|
| 5 | Admin token management | ⬜ Not built. `AdminPanel` still only approves/rejects requests | An issued token can't be revoked at all: no route or store function does it (checked 2026-10-12). So a leaked token stays live. Needs `/api/auth/tokens*` |
| 15 | Logout + session edge cases | 🟡 **Mostly built**: the central 401 → logout + `sessionEnded`; and since Rounds 30 and 32, logging out with an unsaved CV edit asks first. Not built: a warning for logging out of a live run with no edit open | Logging out mid-run still leaves that run unreachable from the page. Only a central 401 still loses an edit (`bugs.md` top, item 9) |
| 14 | Admin audit log | ⬜ Not built | Admin actions leave no trail. Needs the log plane (`backend/bugs.md` vault design §5) |
| 11 | Evidence-quality panel | ⬜ Not built. The data is there (`ProfileAssessment`, `ClaimCheck`) | Honest "how well is this backed" view; meaningful once the Fact Check is real |
| 13 | Per-identifier admin grouping | ⬜ Not built. Depends on #5 | Follows #5 |
| 4 | Vertical pipeline stepper | ⬜ Not built. `AgentGraph` is still the only run view | Clarity, not correctness |
| 10 | Time filter + comparison drawer | ⬜ Not built | Convenience |
| 7 | Design-tokens file | ⬜ Not built, and the inline-hex palette has since grown. Still cosmetic | Cosmetic |
| 9 | Sparkline | ⬜ Deliberately blocked on Evaluation being real | A sparkline over placeholder scores would mislead |
| 3 | Lazy panels | ✅ **Built**: `useFetch(path, {active, once})` backs every read-only view (`context.md` → Boot and failure handling) | — |
| 6 | Identity dropdown | ✅ **Built**: `Header.jsx` on `Menu.jsx`, the reusable popover | — |
| 8 | Defensive mounting | ✅ **Built**: per-view `ErrorBoundary` via `App.jsx`'s `panel()` | — |
| 12 | Account page | ✅ **Built**: `Account.jsx`, including the "request more runs" button below zero | — |
| 16 | UI-side admin guard | ✅ **Built**: `Shell` falls back to Pipeline for a non-admin, and `Sidebar` hides the item. Cosmetic by design; `require_admin` is the real check | — |

**Naming note that still applies (#12).** The nav item is **"Account"**, not
"Profile", because "Build Profile" already means the career-data conversation
(line 56 above). Two different senses of "profile" in one sidebar would read as
one feature.

