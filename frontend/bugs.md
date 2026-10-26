# Open work, by criticality — start here (reconciled 2026-10-13)

> One ranked list of everything still open in this folder, checked against the
> frontend, backend and agent code on the evening of 2026-10-10, again on
> 2026-10-12 after Rounds 27–34, and on 2026-10-13 against the backend's
> 10-10 to 10-12 identity and scope work. Everything below this list is the
> history, in date order; each item here points to the round that holds its
> detail.
>
> **Where it stands, 2026-10-14:**
> - Rounds 27–42 closed items 2, 3, 10, 11, 12, 13, 14, 15, 16, 17, 27 and
>   28, most of 9, and the gate-2 boxes' silent paste cut (Round 41, under
>   item 12).
> - **The backend's scope work reopened two frontend items, both now
>   closed:**
>   - 27: the top-up button called the wrong route. ✅ Round 39;
>   - 28: Build Profile's wording was false. ✅ Round 40.
> - **Every 🟠 and 🟡 item this folder can fix alone is done again.**
> - The same work closed item 7, and the Build Profile half of item 6.
> - Also left here: item 9's central 401 (waits on Resume). Item 11 closed in
>   Round 42. **No code item is left that this folder can fix alone.**
> - Everything else waits on another lane. What this folder needs from the
>   backend is in `backend/context.md` → "What the frontend needs from the
>   backend — after frontend Rounds 27–38".
> - **Everything through Round 42 compiles** (item 1: last built 2026-10-14,
>   first try every time, no code change). None of it has run in a browser
>   yet. That's the one critical item left.
>
> **Backend update, 2026-10-13 to 10-15 (no frontend code touched — logged
> here so the next round knows what's available):** restart survival
> (item 21), saved CVs list + delete (item 22), the `outcome` field
> (item 18), the unmatched-line `match_counts` (item 20), `gate_done.gate`,
> and reading `final` off `run_error` everywhere (item 26 / A1) are all
> built and verified backend-side. **Every item in the 🟡 "blocked on
> another lane" list above except 19, 23, 24 and 25 is now a frontend-only
> build**, not a wait. None of it has been wired into a screen yet. Detail
> in each item above and in one consolidated note just below the
> "Rounds 17–26" table.
>
> **Ranking rule:** harm to a user × how often it happens × whether it can be
> fixed now. Re-rank here when something lands; don't reorder the rounds.
>
> **This list supersedes** "Where things stand, in order" (2026-10-09/10 session
> summary) and the action column of the 2026-10-10 backend note, both near the
> end of the file. Numbers are stable for this revision: cite them as
> "`bugs.md` top, item N".
>
> **2026-10-24 — browser test pass (Round 44, Claude): item 1 is closed.** The whole UI ran in a
> browser through nginx (offline run `d0ce5fc6`): login, all four gates, reject → round 2, the CV editor,
> Resume after a server restart, final download, Runs, Knowledge Base, Build Profile, Account, Settings.
> **N2 fixed** (DEC-161). New open items: phone layout breaks (🟠), no delete for profile entries (🟡),
> gate 4 accepts an empty reject reason (🟡), raw agent names in Settings (🟡). Detail: "2026-10-24 (frontend,
> Round 44)" at the end of this file, `context/bugs_audit_fixed.md` #119, `context/testing/frontend/`.
>
> **Found 2026-10-23, not yet numbered into this list (see "2026-10-23
> (frontend)" below, items N1–N2):** gate 4's payload has carried
> `standing_verdict` since 2026-10-22 (🟠, no backend/Agents work needed,
> only `GateScreen` has to read it) and `GAP_DEMO_NOTE` has been wrong since
> the 10-17 offline-write fix (🟡, a one-string `copy.js` correction).

## 🔴 Critical

1. **Rounds 4, 5, 8–15 and 17–42 all compile, but have never run in a
   browser.**
   - ✅ **Round 42 compiled 2026-10-14** in a fourth build that day: 63
     modules, no errors. The bundle changed (`DC6AqmmN` → `Cao4oK8R`, 235.55
     kB), so it was fresh.
   - ✅ **Round 41 compiled 2026-10-14** in a third build that day: 63
     modules, no errors or warnings, `npm install` cached. The JS bundle
     changed (`DFOiDH8W` → `DC6AqmmN`, 235.35 → 235.52 kB), so the build was
     fresh and includes the change.
   - ✅ **Compiled again 2026-10-14** (Frontend lane, on the user's ask), after
     Rounds 27–40.
     - `docker compose build frontend` passed first time, with no code change.
     - Vite 6.4.3 transformed **63 modules** (60 on 10-10, plus the three new
       files: `ChangeList.jsx`, `MarkdownPreview.jsx` and `unsavedEdit.js`),
       with no errors or warnings.
     - `npm install` was a cached layer, so the dependency versions are the
       same as 10-10.
     - `frontend-frontend:latest` was rebuilt. No container was started.
     - Docker Desktop had stopped again and was restarted (`open -a Docker`).
   - Rounds 27–40 had been checked only by reading, diffs, bracket counts,
     import checks and Python mock-ups before this.
   - ✅ **Compiled 2026-10-10** (Frontend lane, on the user's ask): `docker
     compose build frontend` passed first time, with no code change. Vite 6.4.3
     transformed 60 modules with no errors or warnings, and produced the image
     `frontend-frontend:latest`.
   - **What that proves:** no syntax or JSX errors, and every named import
     exists (Rollup fails on a missing export).
   - **What it doesn't:** runtime errors (an undefined name, a wrong property),
     and whether any screen behaves as its round says.
   - **Still to do:** each round's "how to verify", newest first. That needs
     `docker compose up` plus a running backend. Needs an explicit yes every
     time (standing rule).
   - Docker Desktop was not running and had to be started (`open -a Docker`).
   - **No `package-lock.json`.** `npm install` resolves the newest versions in
     range on every build, so a later build can break with no code change.
   - Detail: Round 13 item 1; Rounds 17–42 at the end of this file.

## 🟠 High — fixable in this folder now

27. ✅ **"Request more runs" in Account can't work any more.** New, found
    2026-10-13.
    - ✅ **Done 2026-10-13 (Round 39), compiled 2026-10-14.**
      - Account calls `POST /auth/request-more` through a new
        `requestMore()` in `AuthContext`.
      - Its wording now says the runs land on this same account, with no new
        token and no sign-in.
      - It re-reads the identity each time it opens, so approved runs show up.
      - Pipeline's 403 line points to Account instead of "ask an admin to
        issue a new one".
    - `Account.jsx` → `askForMore()` calls `requestAccess()`, which is
      `POST /auth/request-access` with the user's own name: a **signup**
      request.
    - Since the backend's identity work (`backend/context.md` → "Identity,
      scope & the log plane"), approving a signup for a name that already has
      an account fails, because `create_profile` refuses it.
    - The page still says the request was sent, so a user who has run out of
      runs waits for runs that can never arrive.
    - Fix: call the new authenticated `POST /auth/request-more {note}`. It tops
      up the caller's own token, from the bearer token rather than a typed
      name. The backend's `request_more` docstring flags exactly this.
    - The highest-harm item open: it strands every user who runs out.
28. ✅ **Build Profile's Round 28 wording is false for a non-admin.**
    - ✅ **Done 2026-10-13 (Round 40), compiled 2026-10-14.**
      - The wording now follows the role: a user reads "only you and an
        admin can see and edit your entries here — but every run reads them,
        and evidence search can find them", and "Your saved entries"; the
        admin reads "every account's".
      - A note says the user's own checkpoint answers don't appear in the
        list.
      - A 403 on save reads "This entry isn't yours, so it wasn't changed."
    - New, found
    2026-10-13.
    - Since `visible_entries` (`backend/routes/profile.py`), a non-admin lists
      and edits only their own entries; a foreign `PUT` is 403.
    - So `BUILD_PROFILE_HELP` ("anyone signed in can see and edit them"),
      `BUILD_PROFILE_SAVED` ("everyone's, not just yours") and
      `BUILD_PROFILE_COUNT` ("all users") are wrong, except for the admin, who
      still sees everything.
    - Still true: entries go into the shared collection every run reads, and
      `/search` is unscoped, so anyone signed in can find them through
      evidence search.
    - Also changed: the user's own gate-2 answers have no `owner`, so they're
      now admin-only and no longer appear in that user's list. The screen
      shouldn't imply they will.
    - `GAP_HELP`'s "anyone signed in can read them" stays true through
      evidence search.
    - `BuildProfile.save()` already shows a 403 inline (`err.message`), but as
      "403 Not your entry". Give it a plain sentence.
2. ✅ **The UI never says a run's evidence is the shared demo profile.**
   Closed by Rounds 27 and 28.
   - ✅ **Labelled 2026-10-10 (Round 27), compiled 2026-10-14:** on the start
     screen, on the run's `tailoring:` line, and at the final review under
     "What changed from your CV". `FACT_CHECK_PENDING` no longer says "against
     your profile".
   - ✅ **The rest closed the same day (Round 28), compiled 2026-10-14.**
     The seven strings that called the shared pool "your profile" now say
     "shared profile", and Build Profile's "Your saved entries" heading says
     whose entries they are. Gate 2's help text now says plainly what happens
     to an answer: other people's runs can use it, anyone signed in can read
     it, and private details should be left out.
   - Since the CV routes landed (2026-10-10), a user tailors their **own** CV.
   - Profile Search, CV Reader and the Writer still read the shared synthetic
     `profile` collection, plus every user's Build Profile entries. So a real
     CV can be edited with records that aren't the user's, and the Fact Check
     is still a placeholder.
   - Label it on the start screen and at the final review, the way the sample
     CV is labelled, until the per-user profile lands. The vault design says
     the same: "the Pipeline screen should not claim isolation before then"
     (`backend/bugs.md` → 2026-10-09 design, P3–P4).
   - New, found 2026-10-10.
3. ✅ **Send `client_request_id` on Start.** Closed by Round 29.
   - ✅ **Done 2026-10-10 (Round 29), compiled 2026-10-14.** It's one id per
     *start*, not per click, as had been planned. A retry click after a lost
     answer resends the same id, so the backend returns the run it already
     started. A fresh id per click would never dedupe that retry.
   - The backend dedupes `POST /runs` by it (`backend/bugs.md` → "Rounds 8–10"
     #4).
   - Detail: Round 29 at the end; Round 10; the backend note.

## 🟠 High — blocked on another lane (the frontend side is ready or approximated)

4. **Exact "last redo" warnings at every checkpoint.**
   - Needs `revision` / `max_revisions` on `gate_wait` (Agents lane,
     `utils/human_gate.py`) and `honoured` on `gate_done` (`backend/bugs.md` →
     2026-10-10 frontend, B1).
   - Until then the round label (Round 19) and the general reject notes
     (Rounds 18, 23) approximate it.
   - At checkpoints 1–3, a reject past the limit is still silently treated as
     Approve.
   - Detail: Round 13 item 4; 2026-08-31 item 3.
5. **CV files can be deleted from under the user.**
   - Re-uploading an older, replaced CV and pressing Cancel deletes it.
   - Deleting a CV in Account removes a file a running or paused run still
     needs.
   - The frontend guards only the current CV (Round 20).
   - Detail: `backend/bugs.md` → 2026-10-10 frontend, D1 and D2.
6. **Other users' records show in Build Profile, Knowledge Base and search.**
   - **Half closed by the backend (checked 2026-10-13).** `/profile/entries`
     and `/kb`'s `manual_entries` are owner-scoped (`visible_entries`, 403 on
     a foreign `PUT`). `/search`, and retrieval itself, are not. The
     frontend's side of this is item 28.
   - `/profile/entries`, `/kb` and `/search` have no owner scope, so editing an
     entry can rewrite someone else's evidence.
   - Once the backend returns 403, `BuildProfile.save()` must show it inline,
     like its 405.
   - When owner scoping lands, change `GAP_HELP` and the `BUILD_PROFILE_*`
     strings in `copy.js` with it. Since Round 28 they say that every entry is
     shared and editable by anyone signed in.
   - Detail: Round 7 item 1; vault design §4.
7. ✅ **A re-issued token loses its CV and can't start a run.**
   - Detail: `backend/bugs.md` → 2026-10-10 frontend, A1 (vault §1).
   - ✅ **Closed by the backend (checked 2026-10-13).** CV storage and run
     ownership are keyed by `profile_id` (`routes/cv.py` passes
     `scope.profile_id`), so a re-issued token keeps its account, its CV and
     its runs. No frontend change needed.
8. **Agent memory holds users' real CV lines, shared and not git-ignored.**
   - Not frontend code, but the UI now tells live users their lines are kept
     (Round 26). If the storage rule changes, `copy.js` must change with it.
   - Detail: `backend/bugs.md` → 2026-10-10 frontend, D3;
     `context/bugs_audit_fixed.md` #55.

## 🟡 Medium — fixable in this folder now

9. **An edit at the final review can still be lost.** Two ways: logging out (or
   a central 401) mid-edit; or pressing "new run" after the stream drops.
   Detail: Round 15, "Still able to lose an edit"; Feature 15a.
   **Mostly closed (Rounds 30, 32): only a central 401 mid-edit is left.**
   - ✅ **Both user actions now ask first (Round 30), compiled 2026-10-14:**
     Log out, and "new run" after the stream drops, each show an inline
     confirm while an unsaved edit exists.
   - **Still open:**
     - **A central 401 mid-edit.** The token is already dead, so the edit
       can't be saved. Only a copy-out could help, and that waits on the
       localStorage draft and Resume (Round 15). **Resume's backend half
       landed 2026-10-13** (item 21) — the localStorage draft is still
       frontend work; this stays open until that's built.
     - 🟡 **New, found 2026-10-10 (Round 30): a run stopped while you edit
       takes the edit with it.** Round 21 made `run_stopped` / `run_error`
       clear `run.gate`, so the editor unmounts and the typed text is gone. It
       happens when the same user starts a run in another tab while this one
       is open at the final review. Before Round 21 the screen stayed, and a
       save got a 409 that kept the text (`GATE_CLOSED_EDIT_KEPT`). Fix: keep
       the edited text when the run ends, and show it with a copy button.
       ✅ **Done 2026-10-12 (Round 32), compiled 2026-10-14.** The text is
       kept on the ended run in an amber "your edited CV — not saved" box with
       Copy. Log out, "new run" and a reload still ask before dropping it.
       Only the central 401 is left in item 9.
10. ✅ **A paused run after a backend restart.** Answering gets "404 Unknown run"
    with the buttons still live. Retire the form with a plain sentence, as the
    409 case now does. New, found 2026-10-10 (Round 17).
    - ✅ **Done 2026-10-10 (Round 31), compiled 2026-10-14.** A 404 retires
      the form with "This run is no longer on the server…". The line under the
      run stops promising "reopen it from Runs once it finishes": after a
      restart the run never finishes, and its log is never written.
    - **Still open, needs the backend:** the page can't tell a restart from a
      network blip until the user answers. A real fix is Resume (item 21),
      which would also make the run reopenable.
    - **Backend built 2026-10-13 (item 21).** `GET /api/runs`'s `interrupted`
      field is exactly this signal: `true` only for a gate parked by a worker
      no longer running it (a restart), never for a run still live in
      memory (a network blip, still answerable the normal way once the
      stream reconnects). `POST /api/runs/{id}/resume` makes it reopenable.
      Frontend wiring (a "This run was interrupted — Resume" state instead
      of the current "no longer on the server" retirement) is still open.
    - ✅ **Frontend wired 2026-10-15 (Round 43), not compiled.** Resume on
      Pipeline after a 404 or a dropped stream; Runs marks the row
      "interrupted" with Resume.
11. ✅ **A revoked token goes unnoticed.** In `AuthContext.refresh()` it's two
    lines; over SSE it needs a probe request. Detail: Round 5 item 7.
    - ✅ **Done 2026-10-14 (Round 42), compiled 2026-10-14.**
      - `refresh()` now ends the session on a 401, through the same
        `endSession()` as the central handler.
      - A dropped live stream calls `refresh()` once, as the probe.
      - So a dead token signs the user out with "your session ended", instead
        of a frozen counter or "lost the connection".
    - **Ranked below 12 and 13 on 2026-10-12.** Checked in code: nothing in the
      app can revoke a token. `backend/routes/auth.py` has no revoke route,
      `approve_request` only mints a new token or tops up an existing one, and
      nothing deletes one. A token dies only if `tokens.json` is hand-edited or
      `ADMIN_TOKEN` is rotated. Move it back up when token management (Feature
      5/13) adds a revoke.
12. ✅ **`maxLength={2000}` on the checkpoint feedback box.** The backend now caps
    feedback at 2,000 characters, so a longer note gets a 422. Detail: session
    summary, item 7.
    - ✅ **Done 2026-10-12 (Round 34), compiled 2026-10-14.** It now has
      `maxLength`, plus a count that appears from 1,800 characters, so a paste
      the browser cut to fit doesn't go unnoticed.
    - **Same silent cut, not fixed:** the gate-2 answer boxes have had
      `maxLength={2000}` with no count since Round 8.
      ✅ **Fixed 2026-10-14 (Round 41), compiled 2026-10-14:** each answer box
      gets the same count from 1,800 characters, amber at 2,000
      (`GAP_ANSWER_MAX`, `charCount`).
13. ✅ **The agent graph after a stop or failure.** A failed step keeps its
    "running" dot, and a stopped run's paused step keeps pulsing "waiting". New,
    found 2026-10-10 (Round 21).
    - ✅ **Done 2026-10-12 (Round 33), compiled 2026-10-14.** The step that
      was working shows a red "failed" (on a failure) or an amber "stopped",
      and a review left waiting shows "stopped". A run the server lost (Round
      31) settles the same way.
14. ✅ **Final output: both formats.** Add .md and .txt buttons, "saved as …", and
    a "last draft (not approved)" label. Detail: Round 13 item 11.
    - ✅ **Done 2026-10-12 (Round 36), compiled 2026-10-14.** A saved CV gets
      "Download .md" and "Download .txt" plus a "saved on the server as …"
      line. A finished run whose review didn't approve is labelled "last draft
      (not approved)" in amber.
    - Not done: Round 13's "Start a new run" offer. Pipeline already shows
      "new run" right under the output, and a past run in Runs has nothing to
      start.
    - Found while building it: item 26.
15. ✅ **A readable diff at the final review.** Detail: Round 13 item 9.
    - ✅ **Done 2026-10-12 (Round 37), compiled 2026-10-14.** All four
      parts:
      - "was" / "now" labels on each line, so the pair doesn't rest on red and
        green alone;
      - word-level highlights;
      - cards grouped under section and entry headings;
      - a "records it cites (N)" toggle with each record's text from this run.
16. ✅ **Editor comfort:** reset, a character count, a preview. Detail: Round 13
    item 10.
    - ✅ **Done 2026-10-13 (Round 38), compiled 2026-10-14.** The editor has
      a toolbar with three parts:
      - **Preview / Edit:** a read-only reading view of the Markdown;
      - **Reset to the draft**, with an inline confirm;
      - a character count, amber from 45,000.
17. ✅ **A negative match score draws an invalid bar.** A one-line clamp. Detail:
    Round 5 item 6.
    - ✅ **Done 2026-10-12 (Round 35), compiled 2026-10-14.** Evidence
      search caps a hit's score to 0–100 for both the bar and the "N match"
      label.
    - `StatePanel`'s `Pct` bar has the same unclamped width. Left alone: the
      values it draws are 0–1 by construction (`overall_fit`,
      `must_have_coverage`, `ats_score`). Clamp it too if a score ever comes
      from somewhere unbounded.

## 🟡 Medium — blocked on another lane

18. ✅ **Runs and Account call a failed run "stopped".** Needed `outcome` on the
    run summaries (`backend/bugs.md` → 2026-10-10 frontend, B3). Detail: Round 5
    item 5.
    - **Backend built 2026-10-15.** `GET /api/runs`'s summaries now carry
      `outcome: "done" | "stopped" | "error" | null` (`registry.list_for`),
      derived from the run's own last event — `"done"` for `run_done`,
      `"error"` for `run_error`, `"stopped"` for `run_stopped`, `null` while
      still in progress. Additive: `completed` is unchanged. See
      `backend/bugs.md` → `"2026-10-15 (outcome field)"`.
19. **A failed run shows the raw exception text.** Needs `message` on
    `run_error` (B2 in the same section). **Still open** — `run_error.error`
    is still `f"{type(exc).__name__}: {exc}"`, unchanged this session.
20. ✅ **"Your first run will barely change your CV."** Needed the
    unmatched-line count. Detail: Round 11 item 4.
    - **Backend built 2026-10-15.** The `cv_link` `node_done` event now
      carries a top-level `match_counts: {matched, partial, unmatched}`,
      summed off `line_links` server-side — no need to walk `line_links`
      yourself to decide whether to show the empty-profile warning at gate
      4. See `backend/bugs.md` → `"2026-10-15 (match counts)"`.
21. ✅ **A paused run can't be reopened after a refresh or restart.** The draft
    of a final-review edit still waits on the same Resume (localStorage-side,
    unaffected). Detail: Round 7 item 3; Round 13 items 6 and 14; backend
    gate-4 item 7.
    - **Backend built 2026-10-13.** `POST /api/runs/{id}/resume` — owner-checked,
      never spends another run allowance, 409 if a worker already owns the
      run or it isn't actually parked at a gate. `GET /api/runs`'s summaries
      now carry `interrupted: true` for exactly the rows this applies to (a
      gate parked by a worker that is no longer running it — a worker still
      holding the run in memory is not `interrupted`, just slow to be
      answered). The replayed log already has every earlier event, including
      the open `gate_wait`, so reconnecting the SSE stream after calling
      `resume` reopens the same review screen with no new fields to read.
      See `backend/bugs.md` → `"2026-10-13 (restart survival)"`.
    - ✅ **Frontend wired 2026-10-15 (Round 43), not compiled.** See item 10.
22. ✅ **Saved CVs on Runs and Account:** a badge, a download and a delete.
    Detail: Round 13 item 14; backend gate-4 item 5.
    - **Backend built 2026-10-13.** `GET /api/runs`'s summaries now carry
      `review` (gate 4's verdict dict, or `null`) and `saved` (`bool`). New
      `DELETE /api/runs/{id}/document` — owner-checked (403, never 401), 204
      on success, removes both `.md`/`.txt` files, then 404 on the next `GET`
      ("deleted" and "never saved" read the same on the wire, like every
      other not-found here). Part (a) of the original ask — `OUTPUTS_DIR` on
      a mounted volume so saved CVs survive a redeploy — is a deployment
      change, still open, not frontend's or backend's code to fix. See
      `backend/bugs.md` → `"2026-10-13 (saved CVs)"`.
23. **Gate 2's free "add or correct anything" box.** Needs `free_text` on the
    gate answer. Detail: Round 8.
24. **Undo one change at the final review.** Detail: Round 13 item 8.
25. **`cv_link`'s per-line CV text still rides the stream and the run log.**
    The header and raw text are scrubbed now. Detail: Round 6 item 4; Round 7;
    backend CV item 4.
26. ✅ **A CV saved before a later failure can't be downloaded from the server.**
    Found 2026-10-12 (Round 36).
    - `GET /runs/{id}/document` read `final.export` only from `run_done`
      (`backend/routes/runs.py`).
    - Since 2026-10-10, a step failing after an approved final review sends
      `final` on `run_error` instead.
    - So the page showed "approved — saved" and the two download buttons, but
      the route answered 404. The page then saved its own copy and said why
      (`finalDownloadFallback`).
    - **Backend built 2026-10-15.** `download_document`, `DELETE
      .../document` and `GET /api/runs`'s `review`/`saved` all now read
      `final` off whichever of `run_done`/`run_error` actually carries it
      (`registry.current_export`, one shared lookup instead of three).
      `finalDownloadFallback`'s client-side save is no longer needed for
      this case — the server copy is reachable now — but it's harmless to
      leave in for a run that truly has nothing saved. See `backend/bugs.md`
      → `"2026-10-15 (final on run_error too)"` (A1).

## ⚪ Backlog — features and planned work, not defects

- **Stage 0 §18 screens:** the intake form, the confirm view, the caller's own
  records with versions in Build Profile, and a retrieval-log drawer. Blocked on
  the Agents lane and the profile data layer. Detail: `DELIVERABLES.md` §18, M4.
- **Production nginx and §22 deployment:** gzip, security headers, no `?token=`
  in access logs. Not started. Detail: `DELIVERABLES.md` §18, §22, M6.
- **The critique-review (fifth) gate.** Blocked on the loop-back design. Detail:
  `design.md`, 2026-08-27 addendum.
- **Presentable backlog, in order:**
  - Feature 5 then 13: admin token management. An issued token can't be revoked
    at all: no route or store function does it (checked 2026-10-12, item 11).
    Needs `/api/auth/tokens*`.
  - Feature 14: admin audit log. Needs the log plane.
  - Feature 11: evidence-quality panel.
  - Feature 4: vertical stepper.
  - Feature 10: time filter and run comparison.
  - Feature 7: design tokens.
  - Feature 9: sparkline. Waits on a real Evaluation.
  - Detail: `design.md`, status table.
- **Out of lane, recorded:** `scripts/dev.py up` can't work on this machine and
  has never run (Infra lane). Detail: Round 16.

## ✅ Closed 2026-10-10 to 10-15 — Rounds 27–43 (frontend; 27–42 compiled 2026-10-14, 43 not compiled; none run in a browser)

| Round | What | Closes |
|---|---|---|
| 27 | The evidence is labelled "shared sample profile, not your own": start screen, run line, final review | Item 2 (first half) |
| 28 | No screen calls the shared profile "yours"; gate 2 and Build Profile say who can read and edit what goes in | Item 2 (rest) |
| 29 | Start sends `client_request_id`, one per start, not per click | Item 3 |
| 30 | Log out and "new run" confirm before dropping an unsaved CV edit | Item 9 (two of its ways) |
| 31 | A gate answer's 404 (the server lost the run) retires the form; the line under the run says it can't be finished | Item 10 |
| 32 | A run that ends mid-edit keeps the edit, with Copy, still guarded | Item 9 (the Round 21 case) |
| 33 | The agent graph shows "stopped" / "failed" instead of pulsing on an ended run | Item 13 |
| 34 | The feedback box stops at 2,000 characters, with a count near the limit | Item 12 |
| 35 | Evidence search caps a hit's score to 0–100 (bar and label) | Item 17 |
| 36 | Final output: "Download .md" / "Download .txt", "saved on the server as …", and "last draft (not approved)" | Item 14 |
| 37 | Final review change cards: "was" / "now" labels, word highlights, grouped by section, cited records on expand | Item 15 |
| 38 | CV editor: Preview, "Reset to the draft" with a confirm, a character count | Item 16 |
| 39 | Account's "request more runs" calls `/auth/request-more`; honest top-up wording; the identity re-read on opening | Item 27 |
| 40 | Build Profile's wording follows the owner scope (user vs admin); a gate-2 answers note; a plain 403 sentence | Item 28 |
| 41 | Each gate-2 answer box shows a count near its 2,000-character limit, so a cut paste is visible | Item 12's leftover |
| 42 | A dead token is noticed: `refresh()` ends the session on a 401, and a dropped stream probes once | Item 11 |
| 43 | Resume: a run the server restarted under (or whose stream dropped) picks back up at its review, from Pipeline or Runs; an unsaved final edit of the same run survives it | Items 10 and 21 (frontend half) |

Detail: each round has its own entry at the end of this file.

## ✅ Closed 2026-10-10 — Rounds 17–26 (frontend; compiled 2026-10-10, not run in a browser)

| Round | What | Closes |
|---|---|---|
| 17 | A refused answer (409) retires the gate form, and so does an accepted one; plain wording for 422 and unreachable | Round 13 item 3 |
| 18 | Honest reject note at the final review | Round 13 item 5 |
| 19 | "round N · reopened with a redone version" label and log line | 2026-08-31 item 3 (approximated; item 4 above makes it exact) |
| 20 | `CvStrip` never deletes the current CV on Cancel, a new pick, or Start | New: found when the CV routes landed |
| 21 | Finished / stopped / failed told apart on the Pipeline screen; an open review closes on a stop; "last draft" label; `final` read on `run_error` | Round 13 item 7; Round 5 item 5 (Pipeline half) |
| 22 | "Request edit" → "Approve with a note" at checkpoints 1–3 | Round 13 item 13 |
| 23 | Reject note at checkpoints 1–3 (the redo limit) | New |
| 24 | nginx's 502 page → "cannot reach the backend" everywhere | New |
| 25 | The feedback label says where feedback goes, per checkpoint and mode | Round 13 item 12 |
| 26 | The CV-editor text is honest; covers the demo note | Round 13 item 15 |

Detail: "Rounds 17–26" at the end of this file.

## 2026-10-15 (backend) — what this session's backend work gives the frontend

> Written by the **Backend lane (Claude)**, logging what changed for this
> folder to pick up — no frontend code touched. Covers three sessions,
> 2026-10-13 through 2026-10-15; full detail and verification are in
> `backend/bugs.md`'s own dated sections, linked below. Nothing here has
> been wired into a screen; every item is still "now buildable", not "now
> working".

| What | Backend detail | Closes/unblocks |
|---|---|---|
| `POST /api/runs/{id}/resume` + `GET /api/runs`'s new `interrupted` field | `backend/bugs.md` → `"2026-10-13 (restart survival)"` | Item 21 in full (backend half); the restart-vs-network-blip half of item 10; the Resume half of item 9 (the localStorage draft is still open) |
| `GET /api/runs`'s new `review`/`saved` fields; `DELETE /api/runs/{id}/document` | `backend/bugs.md` → `"2026-10-13 (saved CVs)"` | Item 22 in full (backend half). Part (a), a mounted volume for `OUTPUTS_DIR`, is still open — deployment, not either lane's code |
| The log plane's `run` kind: `GET /api/logs/mine`/`GET /api/admin/logs` now also carry `run_started`/`node_done` (with `duration_s`)/`gate_opened`/`gate_decided`/`run_done`/`run_stopped`/`run_error`/`allowance_spent`/`allowance_refunded` | `backend/bugs.md` → `"2026-10-14 (log plane, run kind)"` | Nothing blocked on this — no frontend item currently asks for a log viewer. Feature 14 ("Admin audit log") in the backlog below can now be built against something real if it's picked up |
| `gate_done` now carries `gate`, matching `gate_wait` | `backend/bugs.md` → `"2026-10-15 (gate name on gate_done)"` | No open item named this directly; see the Contract table above — a replayed log no longer needs to guess which gate a `gate_done` answered |
| `cv_link`'s `node_done` now carries `match_counts: {matched, partial, unmatched}` | `backend/bugs.md` → `"2026-10-15 (match counts)"` | Item 20 in full (backend half) |
| `download_document`, `DELETE .../document` and `list_for`'s `review`/`saved` all read `final` off `run_error` too, not only `run_done` | `backend/bugs.md` → `"2026-10-15 (final on run_error too)"` | Item 26 in full (A1) — `finalDownloadFallback`'s client-side save is no longer needed for this specific case, though harmless to keep for a run with nothing saved at all |
| `GET /api/runs`'s new `outcome: "done" \| "stopped" \| "error" \| null` field | `backend/bugs.md` → `"2026-10-15 (outcome field)"` | Item 18 in full (backend half) |

**Not touched this session, so still exactly as before:** item 19 (`run_error`'s
message is still the raw `f"{type(exc).__name__}: {exc}"` string); A2 (`run_error`
still names no failed step); A3 (cited records still aren't on
`gate_wait.changes`, though the stream-replay workaround still works); item 23
(no `free_text` on the gate answer); item 24 (no undo-single-change); item 25
(per-line CV text privacy decision, deferred by design, not forgotten).

## 2026-10-22 (frontend) — backend changes since 10-15 that this folder should pick up

> Frontend lane (Claude), from reading `backend/bugs.md` 10-16 → 10-22. No code changed.

| Backend change | Frontend impact |
|---|---|
| `run_error` carries `node` (the agent in flight, or `null` outside a step), 10-21, A2 | Round 33 guesses the failed step from the last "working" dot. Read `ev.node` instead in `applyEvent`'s `run_error` case, and in `extractFinalArtifacts`. With `null`, say "failed outside a step" and don't mark any dot. |
| `POST /runs` can 503 "No CV is configured on the server." before spending a run (10-22, #42) | `PipelineView.start` shows `err.message` raw ("503 …"). Map 503 to a plain `copy.js` sentence (nothing was spent; ask an admin). |
| A damaged run log no longer 500s on `/log`, `/document`, `DELETE …/document`, `/resume` (10-16) | Check the new status in `backend/bugs.md` "2026-10-16 (damaged run log)" against `RunsView`'s `Failed` card and `resumeRun`'s `RESUME_FAILED`. Both already show `err.detail`, so nothing is likely to break. |

## 2026-10-23 (frontend) — two more agent-side changes found while re-reading `context/context.md`; no code changed

> Frontend lane (Claude), read-only this session (no build, no run). Checked
> against `agents/profile.py` and `utils/human_gate.py` as they stand today.
> Both items below are **frontend-only builds** — nothing is blocked on
> backend or Agents, and neither needs a test or a live run to act on.

N1. 🟠 **New: gate 4 already carries a "the reviewer still objects" warning (`standing_verdict`, built 2026-10-22) — nothing in the frontend reads it.**
    - `utils/human_gate.py:standing_verdict()` is wired into
      `GATE_EXTRAS[FINAL_GATE]` next to `changes` (`context_Agents+Orchestration.md`
      #60 item 2, `DEC-027`): it fixes the exact gap `backend/bugs.md`'s B1
      and `bugs_audit_fixed.md` #78 flagged — a run forced past the revision
      cap used to reach the final gate with no sign that the Critic or
      Verifier still objected to the draft.
    - **No backend change needed:** `worker._park` already forwards every
      `gate_wait` payload key outside `_PAYLOAD_NOT_PASSED`, so
      `standing_verdict` is already arriving on the final gate's `gate_wait`
      event today, for every run, whether or not the frontend reads it.
    - **Shape**, present only when something still stands against the draft
      (an empty `{}` otherwise — same contract as `gap_questions`, so the key
      is always there):
      ```json
      {
        "critique": {
          "verdict": "revise",
          "items": [{"rubric_item": "...", "severity": "...", "location": "...", "instruction": "..."}]
        },
        "verifier_report": {
          "status": "fail",
          "claims": [{"claim": "...", "label": "...", "evidence_id": "..."}],
          "do_not_claim_hits": [{"text": "...", "matched_entry": "..."}]
        }
      }
      ```
      A passing verdict is deliberately never carried (noise in a form is
      how a real warning gets skipped) — either sub-key's absence means that
      checker has nothing outstanding.
    - **Impact today:** the Critic half is live (Critic is a real brain);
      the Verifier half is dormant until `verifier` leaves `STUB_NODES`.
      Right now a reviewer approving the final gate after a capped-out
      revise loop sees nothing different from a clean pass — the one review
      that ships the CV is the least informed moment in the run.
    - **Needs:** `GateScreen` at the final gate reads `gate.standing_verdict`
      (would arrive the same way `gate.changes`/`gate.gapQuestions` already
      do, via `PipelineView`'s `gate_wait` fold) and, when it's non-empty,
      shows a warning block above Approve/Edit listing the still-open Critic
      items (`rubric_item`/`severity`/`location`/`instruction`) and/or
      Verifier claims/do-not-claim hits, in plain language (`copy.js`).
    - Found by grepping `standing_verdict` across the repo: it's described in
      `context/context.md`, `context_Agents+Orchestration.md`,
      `bugs_audit_fixed.md`, `decisions.md`, `logic.md` and `flow.md` —
      nowhere in `frontend/`.

N2. 🟡 **New: `GAP_DEMO_NOTE` overstates what a demo-mode gap answer does, since the 2026-10-17 offline-write fix.**
    - The string (`copy.js`) reads: *"Demo mode doesn't read what you type —
      if you answer anything, one fixed example answer is added to the
      shared profile in its place."* Shown at gate 2 whenever
      `run.mode === "offline"` (`GateScreen.jsx:247`).
    - `agents/profile.py:enrich()` was fixed 2026-10-17 (bug #73.6 —
      "an offline run wrote the fixture's answer into the real profile
      store and Chroma, where later live runs retrieved it as real
      evidence"): it now calls `save_gap_answers` only when
      `not config.fake_llm_active()` (a `SAVE_OFFLINE` module flag, default
      `False`, exists only for one test script to opt back in). Checked in
      the tree today: a demo/offline run's gap answers — fixed stand-in or
      not — go into that run's own `evidence` only and are never written to
      `manual_entries.json` or the shared Chroma collection.
    - So the string is now backwards: nothing is added to the shared
      profile in demo mode any more, fixed answer or otherwise.
    - **Needs:** reword `GAP_DEMO_NOTE` to say the fixed stand-in answer
      stays in this run only and isn't saved anywhere (not "added to the
      shared profile in its place"). `FEEDBACK_LABEL_DEMO` and
      `FINAL_EDIT_HELP_DEMO` (gate 4's demo strings, a different code path —
      `final_review.close_run`/`record_learning`, not `enrich()`) are
      unaffected and already correctly say demo runs aren't kept.
    - Not cross-filed anywhere: the Agents-side write-up
      (`context_Agents+Orchestration.md` #73 item 6) only flags this as
      closing *their* bug; it doesn't mention the now-false frontend string.

---

# Bugs / Build plan — access-token login + final CV display fix

> Planned 2026-08-09. Two problems tracked here; see checkboxes for progress.

> **2026-08-19 — backend structure superseded.** The backend build is now planned in
> `backend/context.md` + `backend/bugs.md` (status section at the bottom of that file).
> Two things below are stale for **structure only** — routes, response shapes, and
> status-code rules in this file are unchanged and still authoritative:
> - **Not** a single grown `frontend_api.py` + top-level `auth/` — a `backend/`
>   package, with `scripts/frontend_api.py` reduced to a re-export shim.
> - **Not** `threading.local()` for the fake-LLM switch (the "§1"/"§2" thread-local
>   snippet appears twice below) — `contextvars.ContextVar`. Verified against the
>   installed `langgraph`: nodes can run on a pooled thread via
>   `copy_context()` even in-process, where a thread-local set in the API worker
>   thread is invisible. See `backend/context.md`, "The one deviation".

## Context

1. **No auth exists anywhere.** Frontend and backend are both fully open. Want
   a lightweight login system with two roles (`user`, `admin`). Users
   self-request access; an admin approves and issues a token good for exactly
   2 pipeline runs. The logged-in identity + role show top-right at all times
   — there is currently no header/top-bar component at all (only a left
   `Sidebar`), so one has to be built.

2. **The final CV/cover-letter never actually reaches the user.** Root cause:
   in `scripts/frontend_api.py:78-83`, `GATE_AFTER["verifier"] = "Final
   document review"` pairs the *last* gate with the **verifier** node's
   artifact, not the **document** node's artifact. So
   `PipelineView.jsx:137` (`artifact={run.artifacts[run.gate.node]}`) hands
   `GateScreen` the fact-check report at exactly the moment titled "Final
   document review" — the user is asked to approve a document they're never
   shown. `agents/document.py` is still a stub (returns placeholder text) —
   that's out of scope here (agent "brain" logic stays the project owner's to
   write); this fix is purely about correctly displaying whatever the
   Document agent's artifact currently is, so it's already correct once real
   generation lands later.

Decisions locked in:
- Issuance flow: **self-service request queue** (user requests → admin queue → admin approves).
- Credential type: **single opaque access token** (no username/password, no hashing lib needed).
- Admin bootstrap: **`ADMIN_TOKEN` in `.env`**, unlimited runs, never decremented.

Storage: no DB is wired anywhere in this project (Postgres is configured but
unused). Reuse the existing flat-JSON atomic-write pattern already used twice
(`learning/store.py`, `scripts/frontend_api.py`'s `_read_json`/`_write_json`,
both tmp-file + `os.replace()`). No new Python dependencies —
`secrets.token_urlsafe(32)` generates the token.

---

## Feature 1 — Access-token login system

### Data (new `knowledge_base/auth/` dir, two JSON-array files)

`requests.json` — one record per access request:
```json
{"id": "a1b2c3d4", "identifier": "alice", "note": "...", "status": "pending",
 "created": "2026-08-09T12:00:00+00:00", "resolved": null, "token_id": null}
```

`tokens.json` — one record per issued token:
```json
{"id": "t-9f8e7d6c", "token": "kY3n...", "identifier": "alice", "role": "user",
 "runs_remaining": 2, "created": "...", "request_id": "a1b2c3d4"}
```
Plaintext token, consistent with how `manual_entries.json` already stores raw
data unencrypted — acceptable for this internal tool; not production-grade.

### Backend

**New module `auth/store.py`** (sibling to `learning/`, `agents/`, `state/`):
pure functions, no FastAPI coupling.
- `create_request(identifier, note) -> dict`
- `list_pending_requests() -> list[dict]`
- `approve_request(request_id) -> dict` — generates `secrets.token_urlsafe(32)`, appends to `tokens.json`
- `resolve_token(raw_token) -> dict | None` — checks `config.ADMIN_TOKEN` first (synthetic admin identity, no file write), else scans `tokens.json`
- `consume_run(token_id) -> bool` — atomic decrement of `runs_remaining`; `False` (no decrement) once already 0; admin sentinel always `True`

**`config.py`**: add `ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")`.

**`scripts/frontend_api.py`**:
- `require_auth(authorization: str = Header(None)) -> dict` — parses `Bearer <token>`, 401 on missing/invalid; returns `{identifier, role, runs_remaining, token_id}`
- `require_admin(identity=Depends(require_auth))` — 403 if not admin
- New endpoints: `POST /api/auth/request-access` (open), `POST /api/auth/login` (open), `GET /api/auth/me` (auth), `GET /api/auth/requests` (admin), `POST /api/auth/requests/{id}/approve` (admin, returns the token once)
- Thread `identity: dict = Depends(require_auth)` through every existing handler except `health()`
- `POST /api/runs`: at the top, `if identity["role"] != "admin": if not auth_store.consume_run(identity["token_id"]): raise HTTPException(403, ...)` — **every run consumes one use, offline or live**
- SSE exception: `EventSource` can't set headers — accept `?token=` query param on `GET /api/runs/{run_id}/events` only, validated the same way

### Frontend

- **`AuthContext.jsx`** (new) — plain React context, token persisted in `localStorage`, exposes `login()`, `logout()`, `requestAccess()`, `useAuth()`. Validates a restored token via `GET /api/auth/me` on boot.
- **`api.js`** — module-level token holder + `setToken()`; `get/post/put` attach `Authorization: Bearer <token>`; `openEvents` appends `?token=`.
- **`LoginScreen.jsx`** (new) — token-paste login form + request-access form, toggled locally.
- **`App.jsx`** — wrap in `<AuthProvider>`; gate all existing views behind `if (!token) return <LoginScreen/>`; restructure layout so `<Header/>` sits above the main content area.
- **`Header.jsx`** (new) — top-right badge `"{identifier} · {role}"`, runs-remaining counter for `user` role, logout button.
- **`Sidebar.jsx`** — add an `Admin` nav item, shown only when `role === "admin"`.
- **`AdminPanel.jsx`** (new) — lists pending requests, "Approve" → shows the new token inline for copy/paste hand-off.
- **`PipelineView.jsx`** — wrap `start()`'s `post("/runs", ...)` in try/catch; on 403 show a clear inline error.

---

## Feature 2 — Fix the missing final CV/cover-letter

### Backend: fix gate→artifact wiring

Restructure `GATE_AFTER` to carry an explicit artifact key alongside the title:
```python
GATE_AFTER = {
    "jd_analysis": {"title": "Requirements review", "artifact_node": "jd_analysis"},
    "profile":     {"title": "Evidence review",      "artifact_node": "profile"},
    "matching":    {"title": "Fit review",            "artifact_node": "matching"},
    "verifier":    {"title": "Final document review", "artifact_node": "document"},
}
```
Update `_run_worker`'s `gate_wait` emit to include `artifact_node`.

### Frontend: three small, targeted changes

1. **`PipelineView.jsx`** — `applyEvent`'s `gate_wait` case stores `artifactNode`; `<GateScreen>` gets `artifact={run.artifacts[run.gate.artifactNode]}` **and** `verifierArtifact={run.artifacts.verifier}`.
2. **`GateScreen.jsx`** — when `gate.node !== gate.artifactNode` (final gate only), render **both** the document content and the verifier's fact-check underneath it. Fix header label to "output of Document".
3. **`FinalOutput.jsx`** (new) — a visually distinct "final output" card (document + fact-check), rendered once `run.done` is true in `PipelineView.jsx`, and reused in `RunsView.jsx` for past runs via exported helper `extractFinalArtifacts(events)`.

---

## Order of implementation

- [x] 1. Write this plan to `frontend/bugs.md`
- [x] 2. Feature 2 **frontend**: `PipelineView.jsx` → `GateScreen.jsx` → `FinalOutput.jsx` → `RunsView.jsx`
- [ ] 2b. Feature 2 **backend**: `frontend_api.py` GATE_AFTER → dict-of-dicts (see below)
- [ ] 3. Feature 1 backend: `config.py` → `auth/store.py` → `frontend_api.py` endpoints/dependencies/`/api/runs` gating/SSE token param
- [ ] 4. Manual `curl` smoke test of the auth endpoints
- [x] 5. Feature 1 **frontend**: `api.js` → `AuthContext.jsx` → `LoginScreen.jsx` → `App.jsx` → `Header.jsx` → `Sidebar.jsx` → `AdminPanel.jsx` → `PipelineView.jsx` 403 UX

See **"Backend build plan (planned 2026-08-12)"** at the bottom for the step-by-step
version of items 2b/3/4, written against the real current code.

### Status 2026-08-09 — all frontend work is written, **unverified**; backend outstanding

The whole of `frontend/src` is implemented. Nothing in the app works end to end
until the backend lands, because every request now sends `Authorization: Bearer
<token>` and the app shows `LoginScreen` until `GET /api/auth/me` succeeds.

**Verification status: none worth relying on.** No build has been run. An `esbuild`
bundle of `src/main.jsx` did pass, which shows only that every import resolves and
all JSX parses — it says nothing about Tailwind class validity, React runtime
behaviour, or whether any screen renders. Treat all of it as untested code.
(That check also should not have been run: standing instruction is to **ask before
running the frontend in any form**, throwaway containers included.)

The check to ask for, once the backend is in, is a real build in the existing setup:
`docker compose -f frontend/docker-compose.yml build frontend`. Until `require_auth`
exists or is stubbed, a build is the only meaningful check available.

**Backend contract the frontend now expects** (this is the whole to-do list):

1. `GATE_AFTER` → `{"title": ..., "artifact_node": ...}` per node, with the last
   entry's `artifact_node` being `"document"`; `_run_worker`'s `gate_wait` emit must
   include `artifact_node=`. The frontend falls back to `ev.node` when the field is
   absent, so old run logs still replay — but without this change the final gate keeps
   showing the fact-check instead of the CV.
2. `config.py`: `ADMIN_TOKEN`, `AUTH_DIR`, `DEFAULT_RUN_ALLOWANCE`, plus the
   thread-local `set_fake_llm()` / `fake_llm_active()` pair.
3. `auth/store.py` mirroring `learning/store.py:31-51`, guarded by a module-level
   `threading.Lock()`.
4. `frontend_api.py`: `require_auth` / `require_admin`, the six `/api/auth/*` routes,
   `Depends(require_auth)` on every handler except `health()`, `consume_run` gating on
   `POST /api/runs`, per-owner `_active_runs` dict, ownership checks on
   `answer_gate` / `run_events` / `run_log` / `list_runs`, and `?token=` on the SSE
   route only.

**Response shapes the frontend reads** (keep these exact):
- `GET /api/auth/me` and `POST /api/auth/login` → `{identifier, role, runs_remaining, token_id}`.
  `runs_remaining` must be `null` for admin — `Header.jsx` hides the counter on that.
- `GET /api/auth/requests` → `{"requests": [...]}` with **all** requests, not just
  pending — `AdminPanel.jsx` splits them on `status` itself and renders a resolved
  table. Each record needs `id`, `identifier`, `note`, `status`, `created`, `resolved`.
- `POST /api/auth/requests/{id}/approve` → an object containing `token` (the raw
  string). `AdminPanel` shows it once, inline, with a copy button.
- `POST /api/auth/requests/{id}/reject` → anything JSON; only the status matters.
- `POST /api/runs` must return **403** (not 400/402) when the allowance is exhausted —
  `PipelineView` special-cases that status to say "No runs remaining".

Until then, to test Feature 2 alone, temporarily stub `require_auth` to return
`{"identifier": "dev", "role": "admin", "runs_remaining": None, "token_id": "__admin__"}`.

**Note on the per-user run slots** (item 4 above): root `context/audit.md` finding #6
("global USE_FAKE_LLM race") was closed by joining the old worker before starting a
new run. That workaround is what the run-slot change replaces — reopen #6 there when
this lands, or the two mitigations will be silently fighting each other.

**Also fixed in passing** (not in the original plan):
- `GateScreen`'s `sending` flag was never reset, so the buttons locked permanently
  after one answer — it now resets in a `finally` and shows the error inline. This
  mattered because gate answers can now 403.
- `openEvents` was called without an `onEnd` callback, so a dropped or unauthorised
  stream looked like a hung run. `PipelineView` now flags it.

## Verification

- Feature 2: run an offline pipeline (`USE_FAKE_LLM=1`) through all 4 gates; confirm the "Final document review" gate shows document content + fact-check; confirm the post-completion `FinalOutput` card appears; open that run from the Runs view and confirm the same document shows there too.
- Feature 1: `curl` through the full lifecycle (request-access → approve as admin → login → 2 successful runs → 3rd returns 403). Then through the UI: log out/in, header badge + runs-remaining counter, non-admin never sees Admin nav item, Admin panel approve flow surfaces a copyable token.

## Critical files
- `scripts/frontend_api.py` (gate wiring fix + all new auth endpoints/dependencies)
- `auth/store.py` (new)
- `config.py` (`ADMIN_TOKEN`)
- `frontend/src/App.jsx`, `frontend/src/api.js`
- `frontend/src/components/{PipelineView,GateScreen,FinalOutput(new),RunsView,Header(new),LoginScreen(new),AdminPanel(new),Sidebar}.jsx`
- `frontend/src/AuthContext.jsx` (new)

---

# Backend build plan (planned 2026-08-12)

Written against the real current code (`scripts/frontend_api.py` @ 409 lines,
`config.py` @ 251, `learning/store.py`, `agents/base.py`) and against the frontend
contract as actually implemented in `api.js` / `AuthContext.jsx` / `AdminPanel.jsx` /
`Header.jsx` / `PipelineView.jsx`. **Backend only** — nothing under `frontend/src`
and no agent brain/prompt logic is touched, with one flagged exception (§6).

Steps are ordered so **§4a (Feature 2) is independent of auth** and can land, be
tested, and be committed on its own.

## 1. `config.py` — additive only, ~15 lines

Near the existing path block (`config.py:36-46`) and the `USE_FAKE_LLM` block
(`config.py:59`):

- `KB_AUTH_DIR = KB_DIR / "auth"` — sibling of the existing `KB_*_DIR` constants.
  (The 2026-08-09 plan above called it `AUTH_DIR`; the `KB_` prefix matches every
  other KB path already in the file.)
- `ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")`
- `DEFAULT_RUN_ALLOWANCE = int(os.getenv("DEFAULT_RUN_ALLOWANCE", "2"))`
- Thread-local fake-LLM switch (needs a new `import threading` — `config.py` has none):
  ```python
  _fake_local = threading.local()
  def set_fake_llm(value: bool) -> None: _fake_local.value = value
  def fake_llm_active() -> bool: return getattr(_fake_local, "value", USE_FAKE_LLM)
  ```
  **Why:** `frontend_api.py:243` currently does `config.USE_FAKE_LLM = ...` — a
  process-global mutation performed from a worker thread. One-run-at-a-time hides it
  today; once runs are per-owner (§4f) two concurrent runs in different modes corrupt
  each other, and an "offline" run can silently start making real, billed provider
  calls. Logged as `context/bugs.md` #3.

Also add to `.env.example`, under a new "Frontend access control" heading:
`ADMIN_TOKEN=` and `DEFAULT_RUN_ALLOWANCE=2`.

## 2. `.gitignore`

`tokens.json` holds plaintext credentials and `knowledge_base/` is otherwise
committed, so without this the first approval commits a live token:

```
knowledge_base/auth/
```

## 3. New package `auth/` — `auth/__init__.py` + `auth/store.py`

Pure file I/O, **no FastAPI import**, mirroring `learning/store.py:31-51`
(tmp file + `os.replace`), plus a module-level `threading.Lock()` that
`learning/store.py` does not need — that one is CLI-driven, this one is hit by
concurrent HTTP handlers, so every read-modify-write must be serialised.

Files: `knowledge_base/auth/requests.json`, `knowledge_base/auth/tokens.json`,
both JSON arrays, `mkdir(parents=True, exist_ok=True)` on write.

| function | behaviour |
| --- | --- |
| `create_request(identifier, note)` | `{id, identifier, note, status:"pending", created, resolved:None, token_id:None}` |
| `list_requests()` | **all** requests, not just pending — `AdminPanel.jsx` splits on `status` itself and renders a resolved table |
| `approve_request(id)` | `secrets.token_urlsafe(32)`; appends to `tokens.json` with `runs_remaining = config.DEFAULT_RUN_ALLOWANCE`; flips the request to `approved` + `resolved` + `token_id`; returns a dict **containing the raw `token`** (shown exactly once by `AdminPanel`). Raises if already resolved so a double-click cannot mint two tokens. |
| `reject_request(id)` | flips to `rejected` + `resolved` |
| `resolve_token(raw)` | `config.ADMIN_TOKEN` checked first (only when non-empty) → synthetic `{"id": "__admin__", "identifier": "admin", "role": "admin", "runs_remaining": None}`, no file write; else scan `tokens.json`. Compare with `secrets.compare_digest`. |
| `consume_run(token_id)` | under the lock: `__admin__` → `True`, no write; else `False` if `runs_remaining <= 0`; otherwise decrement, persist, `True` |

## 4. `scripts/frontend_api.py`

**4a. Gate→artifact fix (Feature 2 — independent of auth, land this first).**
`GATE_AFTER` (line 78) becomes dict-of-dicts `{"title", "artifact_node"}`, last entry
`"verifier"` → `artifact_node: "document"`. Then in `_run_worker` (lines 257-259):
`run["gate"] = {"after": node, **GATE_AFTER[node]}` and the emit gains
`artifact_node=`. `PipelineView.jsx:41` already falls back to `ev.node`, so old run
logs replay unchanged.

**4b. Auth dependencies.**
- `require_auth(authorization: str = Header(None)) -> dict` — parse `Bearer <token>`
  case-insensitively; 401 on missing/malformed/unknown; returns
  `{identifier, role, runs_remaining, token_id}` with `runs_remaining=None` for admin
  (`Header.jsx` hides the counter on exactly that).
- `require_admin(identity = Depends(require_auth))` — 403 if `role != "admin"`.

**4c. Six routes** (paths taken from the frontend's actual calls):

| route | guard |
| --- | --- |
| `POST /api/auth/request-access` | open |
| `POST /api/auth/login` | open — body `{token}`, returns the identity shape |
| `GET /api/auth/me` | auth |
| `GET /api/auth/requests` | admin — `{"requests": [...]}` |
| `POST /api/auth/requests/{id}/approve` | admin — object containing `token` |
| `POST /api/auth/requests/{id}/reject` | admin |

`request-access` is unauthenticated and world-writable, so it needs a floor: reject
empty/oversized `identifier`/`note`, and refuse a second pending request for the same
identifier. Otherwise it is an unbounded append-to-disk from any origin.

**4d.** Thread `identity: dict = Depends(require_auth)` through **every** existing
handler except `health()` — `config_view`, `kb_overview`, `kb_file`, `search`, all
`/runs*`, all `/profile/entries*`.

**4e. `POST /api/runs`:** after the live-key check,
`if identity["role"] != "admin" and not auth_store.consume_run(identity["token_id"]):
raise HTTPException(403, "No runs remaining")`. Must be **403** exactly —
`PipelineView.jsx:79` special-cases that status. Consumed on every run, offline or live.

**4f. Per-owner runs.** `_active_run: dict | None` (line 215) → `_active_runs:
dict[str, dict]` keyed by `token_id`; `run["owner"] = identity["token_id"]`; `_abort`
+ `thread.join` apply only to the **caller's** previous run, never another user's. Add
ownership checks (404, not 403, so run existence does not leak) to `answer_gate`,
`run_events`, `run_log`, and filter `list_runs` by owner — which means persisting
`owner` into the run-log JSON in `_run_worker`'s `finally` (line 280) and tolerating
old logs that lack the key (treat those as admin-only). Admin sees everything.

**4g. SSE token.** `GET /api/runs/{run_id}/events` takes `token: str | None = None`
as a query param instead of `Depends(require_auth)` (EventSource cannot set headers)
and validates it by hand through the same `resolve_token` + ownership path. This route
only.

**4h.** `_run_worker` line 243 → `config.set_fake_llm(run["mode"] == "offline")`,
called **inside** the worker thread so it lands on the right thread-local.

Also refresh the module docstring's endpoint table (lines 10-23) — it is this file's
own contract listing.

## 5. Smoke test

`curl` (or `scripts/smoke_auth.sh`): request-access → log in as admin via `ADMIN_TOKEN`
→ list requests → approve → log in with the issued token → `/auth/me` → 2 offline runs
→ 3rd returns **403** → confirm a second token's run is not visible to the first. Plus
one `USE_FAKE_LLM=1` run through all 4 gates asserting the final `gate_wait` carries
`artifact_node: "document"`.

## 6. The one change outside the backend bridge — needs a decision

`agents/base.py:52` and `agents/base.py:99` read `config.USE_FAKE_LLM` directly. For
§1's thread-local to have any effect at all, both must become
`config.fake_llm_active()`. That is a 2-line mechanical substitution with no
prompt/brain logic involved — but it is inside `agents/`, which is fenced off.

- **(a)** assistant makes exactly those two edits;
- **(b)** user makes them;
- **(c)** skip — keep the global mutation, drop the thread-local from §1, and accept
  that concurrent runs in different modes are unsafe.

(c) leaves a real footgun: an "offline" run that silently bills the Groq key.

## Cross-references
- `context/bugs.md` #2 (gate→artifact mismatch) and #3 (global `USE_FAKE_LLM`).
- `context/audit.md` #6 — closed by the join-before-start workaround that §4f replaces;
  reopen/rewrite it when this lands.

---

# Frontend feature backlog — adapted from a reference dashboard spec (2026-08-18)

The user pasted a spec for an unrelated monitoring dashboard (public dashboard +
admin console + access page, model/risk charts, backtests). Most of it is
domain-specific to that other system and does not transfer. Below is only the
part that genuinely fits *this* project — same terminal/dark aesthetic, no
component library, no chart library, no router, no TypeScript, single bridge
file (`scripts/frontend_api.py`) — written as backlog items in the same style
as Feature 1/2 above. None of this is scheduled; pick what's worth building.

## Feature 3 — Lazy panels (cut boot cost)

**Problem:** `App.jsx` mounts all 5 views at once (`pipeline`/`kb`/`build`/
`runs`/`settings`, CSS-hidden, not unmounted) — every view's `useEffect` fires
on load regardless of which tab is visible, so opening the app fires requests
for screens nobody's looking at yet.

**Idea:** a small reusable `Panel.jsx` (mirrors the reference spec's
`panel.js`): wraps a view, fetches its data only the first time it becomes
visible (`active` prop, same pattern `KnowledgeBase`/`RunsView`/`SettingsView`
already half-use via their own `active` prop — this generalizes it into one
place), caches the result so switching tabs back doesn't re-fetch, shows a
"try again" affordance on a failed fetch instead of silently staying blank.

## Feature 4 — Vertical pipeline stepper with a technical-detail layer

**Problem:** `AgentGraph.jsx` is a horizontal node graph — reads well as a
live status view, but has no plain-language explanation of what each agent
*does*, and `design.md`'s own "no jargon" requirement (RAG → "evidence
retrieval", etc.) is only followed in a few spots.

**Idea:** an optional second view of the same run — a vertical stepper, one
numbered block per agent + each of the 4 gates (11 blocks total), each
collapsible:
- plain "what this step does / why it matters" line (new `copy.js` — one file
  holding every plain-language string, so wording stays consistent and is
  easy to audit against `design.md`'s jargon-free list)
- a status dot reusing `AgentGraph.jsx`'s existing status colors
- a nested "technical detail" panel — this is exactly `renderArtifact()`
  from `StatePanel.jsx` already, just relocated per-step instead of in a grid
- deep-linkable: `#step-jd_analysis` etc. in the URL hash, so a link to "the
  matching step of run X" can be shared/bookmarked without a router library
  (plain `window.location.hash` + `hashchange` listener is enough here)

This is additive, not a replacement — `AgentGraph.jsx` stays as the at-a-glance
live view; the stepper is a "explain this run to someone" mode.

## Feature 5 — Admin panel: manage issued tokens, not just approve requests

**Problem:** `AdminPanel.jsx` (per the plan above) only lists pending requests
and approves them. There's no way to see who's holding a token, revoke one, or
top up someone who legitimately needs a 3rd run.

**Idea**, once the backend auth plan lands:
- `GET /api/auth/tokens` (admin) — list issued tokens with `identifier`, `role`,
  `runs_remaining`, `created`
- `POST /api/auth/tokens/{id}/revoke` — sets `runs_remaining = 0`
- `POST /api/auth/tokens/{id}/grant` — body `{extra_runs: int}`, adds to
  `runs_remaining`
- A second table in `AdminPanel.jsx` below the requests queue: search by
  identifier, a "revoke" and "grant +1" button per row. Simple text filter is
  enough — no need for the reference spec's bulk multi-token-per-user grouping
  unless one identifier ends up holding more than one token in practice.

## Feature 6 — Identity as a small dropdown, not a static badge

**Problem:** `Header.jsx` (per the plan) is a static `"{identifier} · {role}"`
span plus a separate logout link.

**Idea:** turn it into one small dropdown (`identifier · role ▾`) opening a
tiny menu with "runs remaining" (if applicable) and "log out" — one reusable
`Menu.jsx` (click-outside-to-close, `Escape` to close) that this and any
future per-row action menu (e.g. Feature 5's revoke/grant, if that grows past
inline buttons) can share, instead of every component reinventing a popover.

## Feature 7 — A small design-tokens file instead of inline hex classes

**Problem:** colors are inline Tailwind arbitrary values (`text-[#d7d9de]`,
`border-[#26282e]`, …) repeated across every component — consistent today
because one person wrote it all in one sitting, but easy to drift.

**Idea:** a `frontend/src/tokens.css` (or a small `tokens.js` object if you'd
rather keep it in JS) defining the palette once — base surface/border/text
colors plus **one accent per section** the way the reference spec does it
(e.g. blue for Pipeline, violet for Admin, green for Build Profile) — as CSS
custom properties (`--surface`, `--border`, `--text-dim`, `--accent`) consumed
via Tailwind's `[var(--accent)]` arbitrary-value syntax so no component code
changes shape, just which literal hex each class references. Optional and
purely cosmetic — skip if the current single dark palette feels fine.

## Feature 8 — Defensive mounting (one broken panel shouldn't blank the app)

**Problem:** there's no error boundary anywhere — if any one view throws
during render (e.g. a malformed KB record, an unexpected SSE payload shape),
React unmounts the whole tree, taking every other view down with it.

**Idea:** a minimal `ErrorBoundary.jsx` (the one place a class component is
actually required — React has no hook equivalent) wrapped around each of the
5(+ admin) views individually in `App.jsx`, showing "this panel hit an error —
{message}" in place of just that view. Cheap, and matches the reference spec's
"defensive init" principle without needing its per-script try/catch scaffolding
(React's error boundary does the same job here, one component instead of many).

## Feature 9 — Hand-rolled sparkline for run history

**Problem:** no charts exist anywhere in the app yet; `RunsView.jsx` is a flat
list.

**Idea:** once `Evaluation`/`Matching` agents produce real scores (currently
stubs — not blocking on that to build the component), a small canvas or
inline-SVG sparkline (~40 lines, no library, matches `design.md`'s "no
decorative elements" + this project's existing no-dependency stance) plotted
above the Runs list: fit-score or eval-score per run, most recent on the
right. Reuse for a single-number "trend" indicator next to a run's summary
row. Skip entirely until there's real score data to plot — a sparkline of
placeholder stub values would be actively misleading.

## Feature 10 — Runs view: time filter + a comparison drawer

**Idea:** two small, independent additions to `RunsView.jsx`:
- a simple date-range filter above the list (`All / 7d / 30d`), client-side
  only (filter the already-fetched `GET /api/runs` list — no backend change
  needed at this run volume)
- clicking two runs (checkbox per row) opens a `Drawer.jsx` (already exists,
  reused) showing their `FinalOutput`/fit-report/eval-score side by side —
  useful once you're iterating on the knowledge base and want to see if a run
  actually got better

## Feature 11 — An "evidence quality" panel from data already computed

**Problem:** the Profile agent already computes a `strong / partial / none`
verdict per requirement (`ProfileAssessment`) and the Verifier already
produces pass/fail claim checks — both are shown today as raw artifact JSON in
`StatePanel.jsx`, but nothing summarizes them the way the reference spec's
"data-quality checks" section does (pass-rate bars + one verdict sentence,
full table behind "show more").

**Idea:** a small presentation-only component, `EvidenceQuality.jsx`: one
plain-language verdict line ("3 of 4 requirements are well supported by your
profile"), a pass-rate bar per requirement (strong/partial/none as 3 stacked
segments), full per-requirement gap questions behind a "show details" toggle.
Pure rendering over data the backend already returns — no new endpoint.

## Feature 12 — Self-service account page ("My Account")

**Naming note:** the app already has a "Build Profile" view (`BuildProfile.jsx`)
— that's about building your *career* profile (projects, skills, etc.) for the
knowledge base, a completely different meaning of "profile." Call this new
screen **"Account"** in the sidebar, not "Profile," so the two don't collide in
the nav. ("Profile" as a label is fine in conversation — just not as the nav
item text.)

**Problem:** once logged in, a user has no page of their own — no way to see
their own identifier/role/runs-remaining except the small `Header.jsx` badge,
and no way to see just their own run history without it being mixed into a
general Runs list (moot today since regular users only ever see their own runs
per the ownership model in the backend plan §4f — but that's implicit, not
shown anywhere as "this is your account").

**Idea:** a new `Account.jsx` view (6th sidebar item, visible to both roles,
unlike the admin-only Admin panel):
- identifier, role, runs remaining (reuse `useAuth()` — all of this is already
  in `AuthContext`, no new endpoint needed for the basics)
- a short list of the user's own past runs (calls the existing `GET /api/runs`,
  already owner-filtered for non-admins)
- **"request more runs" button**, shown once `runs_remaining` hits 0 — calls
  the same `requestAccess()` the pre-login screen uses, pre-filled with the
  user's own identifier. This matters: today, once a token is exhausted, the
  only path back is to log out and go find the request-access tab again on
  `LoginScreen`. Letting them request from inside the app (still "logged in"
  on a spent token, since login only checks the token *exists*, not that it
  has runs left) closes that loop.

## Feature 13 — Admin: per-identifier history, not just per-token

**Problem:** Feature 5's token table (revoke / grant-extra-runs) is per
*token*. Since a new request+approval mints a brand-new token record, the same
person requesting access twice (e.g. after exhausting their first token)
shows up as two disconnected rows with no link between them.

**Idea:** group `GET /api/auth/tokens` client-side by `identifier` in
`AdminPanel.jsx` — one expandable row per person, their tokens nested inside
(issued date, runs remaining, revoke/grant per token), plus a lifetime total
("6 runs used across 3 tokens"). Pure client-side grouping over data the
endpoint already returns — no backend change beyond what Feature 5 already
needs.

## Feature 14 — Admin audit log

**Problem:** admin actions (approve, reject, revoke, grant-extra-runs) leave
no trail — if a token gets revoked, there's no record of when or why, which
cuts against this project's own pattern of auditing everything else (state
snapshots at every human gate, a full run-event log per pipeline run).

**Idea:** `auth/store.py` gets one more function, `log_action(action, target_id,
detail)`, called at the end of `approve_request`/`reject_request`/`revoke`/
`grant`, appending to `knowledge_base/auth/audit.json` (same atomic-write
pattern as the other two auth files). New admin-only endpoint `GET
/api/auth/audit`, rendered as a flat chronological list in a new "Audit"
section of `AdminPanel.jsx` (or its own sidebar item if it grows — a section
within Admin is enough to start). Since there's currently exactly one admin
identity (`ADMIN_TOKEN` from `.env`), "which admin did it" is moot for now —
the log is still worth having for *when* and *what*, and the field is there
for free the day a second admin exists.

## Feature 15 — Logout & session edge cases

Two small but real gaps once login/logout is a real feature people use daily:

- **Logout while a run is active:** logging out just clears the local token —
  the pipeline run keeps executing server-side (it's a detached worker
  thread), but the live SSE view is gone and, depending on how `run_events`
  auth ends up implemented, reconnecting after logging back in may or may not
  reattach to it. Cheapest fix: `Header.jsx`'s logout button checks whether
  `PipelineView` has a run in flight (lift a tiny `isRunActive` flag up via
  `AuthContext` or a shared ref) and shows a one-line confirm ("a run is still
  in progress — log out anyway?") instead of logging out silently.
- **Token revoked mid-session:** if an admin revokes a user's token while
  they're actively using the app, the *next* API call will 401, but nothing
  today reacts to that centrally — each call site would need its own check.
  Fix once, in `api.js`: any `401` response from `get`/`post`/`put` calls a
  shared `onUnauthorized()` callback (wired to `AuthContext.logout()` plus a
  message: "your session ended — ask an admin for a new token") instead of
  just rejecting the promise for that one call site to handle (or not handle).

## Feature 16 — Don't let the UI render admin screens for non-admins

**Problem:** `App.jsx`'s view-switching is just a `useState` string — nothing
stops `view` from being set to `"admin"` for a non-admin (e.g. by editing
React devtools state, or if a future change adds a stray link). The backend
already 403s any admin-only call, so this isn't a real security hole, but the
UI would still try to render `AdminPanel.jsx` and show empty/erroring tables
instead of failing cleanly.

**Idea:** one guard where `view` is set (or where the admin panel is rendered)
— `if (view === "admin" && role !== "admin") return <Pipeline/>` (or simply
never render the admin `<div>` block at all when `role !== "admin"`, matching
how the Admin nav item is already conditionally hidden in `Sidebar.jsx`). Two
lines, cheap defense-in-depth alongside the nav-hiding that's already planned.

## Explicitly dropped (spec ideas that don't fit this project)

- **"Awaiting manual execution" queue** — that reference system's backend
  never runs anything itself (a human executes a printed CLI command). This
  project's backend *does* run the pipeline itself (`graph.stream()` in a
  worker thread) — there's nothing to queue for manual execution.
- **Username/password + session cookies + CSRF + lockout** — superseded by
  this project's own locked-in decision: single opaque access token, no
  passwords, no hashing dependency. Re-open only if that decision changes.
- **"Redeem token → returns the exact CLI command, never executes it"** —
  same reasoning as above; this app executes runs directly, it doesn't hand
  back a command to run elsewhere.
- **Cache-busted asset URLs (`?v=...`)** — Vite's production build already
  content-hashes every asset filename; a manual version query string would be
  redundant.
- **Model leaderboard / backtest / drivers panels** — specific to that other
  system's ML-model-comparison problem; this project has no equivalent
  concept (Feature 9/10 above are the closest fitting analogues: score
  history and run comparison).

---

# Round 2 — resilience, honest failures, Account page (built 2026-08-19)

Frontend only. Everything below is **written but unrun** — see "How to verify".

## Why this round, and what the backlog got wrong

Auditing the Feature 3–16 backlog against the real tree before building it turned up
three corrections worth keeping:

- **Feature 16 was already done** — `App.jsx` guards the admin view twice (state
  fallback *and* conditional mount). No work needed.
- **Feature 3's premise was false.** It claims "every view's `useEffect` fires on
  load". They don't: `KnowledgeBase`, `RunsView` and `SettingsView` already gate on
  `active`, and KB/Settings cache besides. Nothing fetches on boot but the health
  poll. The real gap it was pointing at was the missing **error/retry** half.
- **Features 9 and 11 would have rendered fabricated data.** `agents/matching.py:21-27`
  hardcodes `overall_fit = 0.45` with `matches=` commented out; `agents/evaluation.py`
  returns an all-null `EvalRecord`; and `ProfileAssessment` — the strong/partial/none
  verdict Feature 11 wants — is computed at `agents/profile.py:74` but `GraphState`
  has no field for it (`state/state.py:203-229`), so `profile.py:89-91` throws it
  away. Both deferred.

## What changed

**Boot is now legible.** The app previously could not be entered at all: `/auth/me`
404s (no backend auth yet), so every path led to a login form whose POST also 404s,
surfacing as a bare `"404 Not Found"`. Now `AuthContext` probes `/auth/me` on boot
*whether or not a token is stored* and classifies: `401` → login screen (auth is live,
you just aren't), `404` → new `BackendError` card saying the auth endpoints are not
deployed, `0`/`5xx` → unreachable — each with a Retry. `api.js` normalises network
failures to `ApiError(0, …)`, since a `fetch` rejection otherwise throws a bare
`TypeError` with no `.status` to branch on.

**Nothing silently swallows errors any more.** New `useFetch.js` (+ `Failed.jsx` card)
replaces the three copies of `.catch(() => {})` that left views stuck on a permanent
"loading…" string, preserving each one's caching semantics (`once: true` for KB and
Settings, `once: false` for Runs). The three previously *uncaught* async calls —
`KnowledgeBase.openFile`, `RunsView.openRun`, `BuildProfile.save` — now surface errors
instead of producing unhandled rejections and a frozen form.

**One panel can no longer take down the app.** New `ErrorBoundary.jsx` wraps each view
individually in `App.jsx`. The crash vectors it would have been catching are fixed at
source too: every field read in `RunLog.jsx`'s `line()` is now optional (`ev.title
.toLowerCase()` threw on any malformed `gate_wait`), and `KnowledgeBase`'s
`recs.length` no longer assumes `res.records` exists.

**Clipboard no longer throws off-localhost.** `FinalOutput` and `AdminPanel` called
`navigator.clipboard.writeText` unguarded — that object is **undefined outside a secure
context**, so Copy threw for anyone opening the app on a LAN IP rather than
`localhost`. New `clipboard.js` feature-detects and falls back.

**Account page + identity menu** (Features 12 and 6). New `Account.jsx` — a 6th nav
item for both roles, deliberately named "Account" so it doesn't collide with "Build
Profile", which means a *career* profile. It shows identity/role/runs-remaining from
`useAuth()` (no new endpoint), the user's own runs from the existing `GET /api/runs`,
and a **"request more runs"** button once the allowance hits 0 — closing a real dead
end, since today an exhausted token forces a logout to reach the request form. New
reusable `Menu.jsx` (click-outside, Escape) turns the header badge into a dropdown.

**Central 401 handling** (Feature 15b). `api.js` gained `setUnauthorizedHandler`;
`AuthContext` wires it to logout + a "your session ended" notice on `LoginScreen`. It
is suppressed for `/auth/login` and `/auth/me`, or a bad-token login would tear down a
session that never existed.

**Stub output is labelled** rather than dressed as findings — new `stubs.js` marks
placeholder `matching` / `evaluation` / `document` artifacts in `StatePanel` and
`FinalOutput`. These are heuristics with a false-positive guard (a genuine zero-match
run scores zero and is left alone); the honest fix is a backend flag on the artifact.
**Delete each entry as its agent becomes real.**

## Still deferred

Features 5, 13, 14 (token management, per-identifier history, audit log) — all need
`/api/auth/tokens*` routes that do not exist. Feature 4 (vertical stepper) — largest
item, additive rather than corrective. Feature 7 (design tokens) — real but cosmetic;
note Tailwind v4 here is CSS-first, so it is an `@theme` block in `index.css`, not a
`tailwind.config.js`. Feature 15a (confirm logout mid-run) — needs run state lifted out
of `PipelineView` purely to inform a dialog.

## How to verify

**Nothing here has been run.** No build, no browser. Import resolution and leftovers
were checked by grep only; that says nothing about Tailwind compilation or runtime.

1. `docker compose -f frontend/docker-compose.yml build frontend` — the only
   meaningful check until the backend lands.
2. Then, with `require_auth` stubbed per the note above: walk Pipeline → KB → Runs →
   Account → Settings, confirming none is stuck on a loading string.
3. Stop the bridge and reload → `BackendError` naming the status, Retry recovers.
4. Emit a `gate_wait` with no `title` → one dead panel, not a blank page.
5. Open via a LAN IP and press Copy on `FinalOutput` → fallback, not a thrown error.

---

# Round 3 — first real build + browser load (2026-08-19)

The backend landed today (see `backend/bugs.md`), so for the first time the
frontend could actually be built and loaded. Two rounds of frontend work had
shipped **entirely unverified**; this is what running it found.

## 🔴 Fixed: `stubs.js` had a syntax error that broke the production build

`docker compose build frontend` failed outright:

```
[build 6/6] RUN npm run build
  ... at getRollupError (rollup/dist/es/shared/parseAst.js)
  17:   // A real fit report cannot score the candidate above zero while matching
```

The top of `frontend/src/stubs.js` held a **duplicated 7-line fragment** of the
`matching` heuristic pasted *above* the file's own header comment, leaving an
orphan `matching: (a) => ...,` object entry at module top level — and the last
duplicated line had the real header comment glued onto its end
(`... > 0,// Several agents are still placeholder ...`). Not valid JavaScript at
any point since the file was written.

**Impact:** the app could not be built at all. Every claim in Round 2's "How to
verify" section was untestable, and the file was authored, reviewed, and
documented across two sessions without anyone running `npm run build` once.
Round 2's own note that "nothing here has been run" was more load-bearing than
it looked.

**Fix:** deleted the 7 duplicated lines. `HEURISTICS` is now defined once,
braces balance, and the build succeeds. No behaviour change — the surviving copy
is byte-identical to the duplicate.

**Lesson:** an `esbuild` bundle check (Round 1) is not a build. It resolves
imports and parses JSX; it did not catch a plain syntax error in a plain `.js`
file, because that file only gets parsed by Rollup during the real Vite build.

## ✅ Verified working in Chrome (localhost:3000, real container, real backend)

- **Container builds and serves.** `docker compose build frontend` →
  `docker compose up -d` → `http://localhost:3000` returns 200, and
  `http://localhost:3000/api/health` returns 200 through the nginx proxy to the
  bridge on the host, so `host.docker.internal:8000` resolves correctly on this
  machine.
- **Boot classification is correct.** With the backend live and no stored token,
  the boot probe `GET /api/auth/me` returns 401 and the app renders
  **`LoginScreen`** — not `BackendError`. That distinction is exactly what
  Round 2 built and it works: 401 means "auth is live, you just aren't".
- **Tailwind v4 compiles and the palette renders.** The dark theme, the arbitrary
  hex values, and the monospace type all render as intended — the first time this
  has been confirmed, since there is no `tailwind.config.js` and every colour is
  an inline arbitrary value.
- **Request-access flow works end to end from the browser.** Toggled to the
  request form, filled name + note, submitted → the green "request sent" panel
  rendered, and the record landed in
  `knowledge_base/auth/requests.json` as `status: "pending"` with the note
  intact. That is browser → nginx → FastAPI → atomic disk write, verified.
- **No console errors or warnings** on load or through the request-access flow.

## Not verified — needs a signed-in session

Everything behind the login wall is **still unverified in a browser**: Pipeline,
Knowledge Base, Build Profile, Runs, Account, Settings, Admin. Signing in means
pasting an access token into a credential field, which the assistant does not do.

To finish the check yourself (~2 minutes), with both services already running:

1. Take `ADMIN_TOKEN` from `.env` and paste it into the sign-in box.
2. Walk Pipeline → KB → Build Profile → Runs → Account → Settings → Admin, and
   confirm none is stuck on a "loading…" string.
3. On **Pipeline**, start a run in *demo mode (no model calls)* and answer all
   four gates. The one to watch is the last, **"Final document review"** — it
   must show the **CV text** with the fact-check underneath it, not the
   fact-check alone. That is the bug this whole round exists to fix, and the
   backend half is confirmed (the run log's last `gate_wait` carries
   `artifact_node: "document"`), but the *rendering* of it has never been seen.
4. On **Admin**, the `browser-check` request submitted during this verification
   is sitting in the pending queue — approving it exercises the token-issue
   panel and the copy button.

Specific things worth a sceptical eye, none of them yet exercised:
- SSE through nginx: `proxy_buffering off` is set, but no live stream has been
  watched in a browser.
- `FinalOutput`'s Copy/Download buttons.
- The runs-remaining pill in the header dropdown (admin hides it; a *user* token
  shows it — approving `browser-check` gets you one).

## Known frontend defect found while reading, not fixed

**`BuildProfile.jsx`'s save-an-edit path posts to the wrong URL.** In `save()`:

```js
const res = entryId
  ? await put(`/profile/entries/`, body)   // <- entryId never interpolated
  : await post("/profile/entries", body);
```

Editing a previously-saved entry therefore hits `PUT /api/profile/entries/`
instead of `PUT /api/profile/entries/{id}`. The backend has no route for that
path, so it 405s and the error surfaces in the form. Creating entries is fine;
only re-editing one saved earlier in the same session is broken. Left untouched
because this round was scoped to making the system build and run — one-line fix
(`` put(`/profile/entries/${entryId}`, body) ``) whenever you want it.

## Still deferred (unchanged)

Features 5, 13, 14 (token management, per-identifier history, audit log) — still
need `/api/auth/tokens*` routes, which the backend build did not add. Feature 4
(vertical stepper), Feature 7 (design tokens), Feature 15a (confirm logout
mid-run).

`stubs.js` can now start shrinking: the backend emits `stub: true` on every
`node_done` event for placeholder agents. Switching `isStubArtifact` to read
`ev.stub` would delete the heuristics file **and** correctly label `critic` and
`verifier`, which are also placeholders (both return a hardcoded PASS) and which
the current shape-based guesses cannot detect at all.

---

## ⚠️ 2026-08-22 — pipeline runs are broken again (backend-side, not a frontend regression)

Nothing in `frontend/src` changed, and the Round 3 verification above still
stands for boot, login screen, request-access, and the container build. But
**starting a run from the UI now fails immediately after the first gate**: you
approve "Requirements review" and the run dies with

```
run_error  AttributeError: 'tuple' object has no attribute 'items'
```

Cause is entirely backend: the graph gained a real `interrupt()`-based gate node
on 2026-08-20 while the bridge kept its own `threading.Event` gates, and the two
collide. See `context/bugs.md` #9 and `backend/bugs.md`.

**What this means for the frontend:** the "not verified — needs a signed-in
session" checklist above is now partly blocked. Signing in, navigating every
view, and the Admin approve flow are all still testable. **Walking a run to the
final gate is not** — so the one thing that most needed a browser check, that
"Final document review" renders the CV rather than the fact-check, still cannot
be seen. The backend half of that fix is confirmed correct on the wire and is
unaffected by #9.

Depending on which option is taken for #9, the frontend may need a change: if the
bridge adopts `interrupt()`/`Command(resume=...)`, gate answers still POST to the
same route and the event stream keeps the same shapes, but `artifact_node` would
be derived from the gate's `interrupt()` payload (which carries `gate`, `field`,
`value`) rather than from the bridge's `GATE_AFTER` table. `PipelineView.jsx`'s
`ev.artifact_node || ev.node` fallback means old logs keep replaying either way.

> **Resolved 2026-08-31 — option 1 was taken.** The bridge now adopts
> `interrupt()`/`Command(resume=...)` on a per-run `SqliteSaver`. See the
> section below for what that means for `frontend/src`.

---

# ⚠️ 2026-08-31 — backend #9/#28/#29/#30 landed; four things the frontend now needs

Backend only so far — **nothing under `frontend/src` has been changed**, and none
of the backend work below has been run. Full write-up on the backend side:
`backend/bugs.md`, "2026-08-31" section.

What changed on the wire:

| change | frontend consequence |
| --- | --- |
| The bridge relays the **graph's** gates (`interrupt()`/`Command(resume=…)`) instead of owning its own | positions, titles and `artifact_node` are unchanged — see below |
| `gate_wait` now carries **`gap_questions`**, and `POST /runs/{id}/gate` accepts **`gap_answers`** | **new UI needed** — item 1 |
| `profile_enrich` now emits `routing` / `node_start` / `node_done` | **new UI needed** — item 2 |
| A rejected gate loops back and the **same gate reopens** in a later round | **behaviour change** — item 3 |
| `stub: true` is now correct (only `document`, `verifier`, `evaluation`) | `stubs.js` can go — item 4 |

**Unchanged, deliberately:** every gate still fires after the same node it used
to (`jd_analysis`, `profile`, `matching`, `verifier`), still carries the same
four `title` strings, and gate 4 still carries `artifact_node: "document"`. So
`PipelineView.applyEvent`, `GateScreen`'s `showsVerifierToo`, and `FinalOutput`
need no changes for the gate rework itself. Old run logs replay unchanged.

## 1. 🔴 Gate 2 still cannot be answered from the UI — the form does not exist

> **Superseded 2026-09-24 by "Round 5 plan — the gap-answer form" at the bottom
> of this file.** That section was traced end to end against the current code and
> adds three things this sketch missed: answers must be dropped on `reject`
> because the graph would otherwise keep them, demo-mode answers are written into
> the real profile, and the exact key-matching rule. Build from that section, not
> this one.

This is the frontend half of `context/bugs.md` #29 and it is the one that
matters. The backend half is done: the gate's questions now reach the browser and
the answer route accepts them. Nothing renders or sends them, so
`state.gap_answers` is still `{}` on every UI run, `enrich()` still early-returns,
and `profile_enrich` still no-ops while reporting success.

`StatePanel.jsx:78` already *displays* `gap_questions` inside the profile
artifact — so the UI shows the candidate the questions and gives them no way to
answer, which is the worst of the three possible states because it looks like a
working feature.

Two changes:

- **`GateScreen.jsx`** — when `gate.gapQuestions?.length`, render one text input
  per question above the feedback box, keyed by `requirement`:
  ```jsx
  // payload shape: [{ requirement: "SQL", question: "Which projects…?" }]
  const [gapAnswers, setGapAnswers] = useState({});
  ```
  Collect into `{ [requirement]: answer }`, skip blanks, and pass the object to
  `onAnswer`. Worth suppressing on `reject` — the CLI driver does exactly that
  (`scripts/run_gated_graph.py:56`, `decision !== "reject"`), since answering an
  interview you just rejected is meaningless.
- **`PipelineView.jsx`** — two lines:
  ```js
  case "gate_wait":
    next.gate = { …, gapQuestions: ev.gap_questions || [] };
  …
  const answerGate = async (decision, feedback, gapAnswers) =>
    post(`/runs/${runIdRef.current}/gate`, { decision, feedback, gap_answers: gapAnswers || {} });
  ```
  `gap_answers` is optional on the backend model (`dict[str, str] = {}`), so
  sending nothing keeps working for gates 1/3/4.

Label it in this spec's own jargon-free vocabulary — "a few things your profile
doesn't cover", not "gap questions".

## 2. ✅ `profile_enrich` is a pipeline step the UI cannot show — **fixed 2026-09-24**

`AgentGraph.jsx`'s `AGENT_TITLES` and `StatePanel.jsx`'s `CARD_TITLES` are both
seven-entry maps written before `profile_enrich` existed (it became a real graph
node 2026-08-26). The bridge used to hide the stage entirely; it no longer does.
So today:

- `RunLog.jsx` prints the raw id — `"profile_enrich started"` — because
  `AGENT_TITLES[ev.node]` misses and it falls back to `ev.node`.
- `AgentGraph` renders 7 nodes and silently drops the 8th, so the pipeline
  diagram no longer matches the run.
- `StatePanel` filters on `CARD_TITLES` keys, so the enrichment artifact is
  fetched, stored in `run.artifacts.profile_enrich`, and never displayed.

Fix is two map entries plus one position in the `AGENTS` order. Suggested
labels, consistent with the existing set ("Profile Search", "Fact Check"):
`profile_enrich: "Profile Update"`, card title `"Answers added to your profile"`.
It sits **between** `profile` and `matching`.

`renderArtifact` needs no new branch — `profile_enrich` returns `{evidence: […]}`,
the same shape the `profile` branch already renders. Either add
`profile_enrich` to that branch's condition or let the key/value fallback
handle it.

## 3. 🟠 A gate can now reopen, and reject no longer ends the run — **approximated 2026-10-10 (Round 19, a client-side round count); exact once `gate_wait` carries round info (top list, item 4)**

Two assumptions in the current UI are no longer true. Both were predicted in
`context/design.md`'s 2026-08-27 addendum ("two existing assumptions this
breaks"); they went live with this backend change.

- **A rejected gate is no longer terminal.** The bridge used to emit
  `run_stopped` and stop. Now `reject` is forwarded to the graph, which sends the
  work back to the agent that produced the artifact (`GATE_PRODUCER`), re-runs
  it, and **reopens the same gate** with the new artifact. `applyEvent` already
  handles a second `gate_wait` correctly, so nothing breaks — but the user gets
  no signal that this is round 2 of the same question, and `RunLog` will show two
  identical `paused — fit review` lines.
- **`run_stopped` now means only "superseded by a new run".** Nothing else emits
  it. `PipelineView`'s `run.done` still covers it.

Minimum useful change: `gate_wait` could carry a round number so `GateScreen` can
say "reviewing the revised version". That field does **not** exist yet — the
backend has `state.revision_count` and `GateFeedback.revision` but does not put
either on the event. Flagging rather than building: say the word and it is a
one-line addition to the `gate_wait` emit in `backend/runs/worker.py`.

## 4. ✅ `stubs.js` now mislabels real Matching output — **file deleted 2026-09-24**

`agents/matching.py` has been a real brain since 2026-08-30 (226 lines, one LLM
pass, its own fit arithmetic). `stubs.js`'s heuristic still flags any `matching`
artifact scoring above zero with an empty `matches` list, so genuine fit reports
render with "⚑ placeholder output". That is the exact failure the backend `stub`
flag was added to prevent, arriving from the frontend side.

The backend's `STUB_NODES` is now correct and minimal — `document`, `verifier`,
`evaluation` — and `node_done` carries `stub: true` for exactly those. So:

- `PipelineView.applyEvent`'s `node_done` case should record `ev.stub` alongside
  the artifact (e.g. `next.stubs[ev.node] = !!ev.stub`),
- `StatePanel` / `FinalOutput` read that instead of calling `isStubArtifact`,
- **delete `stubs.js` entirely.** It also correctly picks up `critic` and
  `verifier`, which the shape heuristics could never detect.

Round 3's closing note already recommended this; it is now actively wrong rather
than merely redundant, because one of the three agents it guesses at has become
real.

## ✅ Also still open from Round 3, and now load-bearing — **fixed 2026-09-24**

**`BuildProfile.jsx:110`** — ``put(`/profile/entries/`, body)`` never
interpolates `entryId`, so editing a saved entry 405s. That was cosmetic when
found. It is not any more: `PUT /profile/entries/{id}` is what now **re-embeds**
the corrected text into the `profile` collection (`context/bugs.md` #30), so
while the URL is wrong, a correction never reaches retrieval and the superseded
text keeps answering queries forever. One line:
`` put(`/profile/entries/${entryId}`, body) ``.

Note also that indexing happens on a **background thread**, so a save returns
before the entry is searchable — the first one in a process waits on a ~440MB
model load. If the UI ever wants to show "indexed", that needs a new endpoint;
today there is no signal.

## Addendum, same day — the remaining backend 🟡s. **No frontend change required.**

`context/bugs.md` #31, #32, #35 and #37 also landed (`backend/bugs.md`,
"2026-08-31 (later)"). Recorded here only because two are visible from the UI:

- **Run history is now actually chronological** (#31 — `list_for` sorted
  filenames, which are random hex, not `started`). `RunsView.jsx` and
  `Account.jsx` both render `GET /api/runs` in the order given and neither sorts
  client-side, so both are simply correct now. Nothing to change; worth knowing
  the list you were looking at before was shuffled, not broken.
- **`POST /runs` now 422s on bad input** (#37 + one found beside it):
  `pace_seconds` outside `0…5`, an empty or >20,000-char `job_description`, and
  a `mode` that is not exactly `"offline"` or `"live"`. `PipelineView.start()`
  already catches the failure and renders `err.message`, and it only ever sends
  those two mode strings and disables Start on an empty JD, so nothing breaks.
  The one rough edge: a 422 body is FastAPI's validation shape, not the
  `{"detail": "..."}` string `api.js` expects, so a pasted 30k-character JD will
  surface a less readable message than it could. Cosmetic; fix in `api.js` if it
  ever comes up in practice.

  > **Wrong on both counts — corrected 2026-09-24.** `api.js` did not expect the
  > `{"detail": ...}` shape; it did not parse the body at all, so **every** error
  > in the app rendered as raw JSON, not just 422s. Fixed in Round 5 below.

---

# Round 4 — three fixes, no new features (2026-09-24)

Frontend only, and deliberately narrow: the three items from the 2026-08-31 list
whose backend halves were already confirmed on the wire. Each precondition was
checked in the backend source before touching anything, not taken from these
notes:

| precondition | verified at |
| --- | --- |
| `PUT /api/profile/entries/{id}` exists, takes `{section, record}`, returns the item | `backend/routes/profile.py:121` |
| `node_done` carries `stub` for `{document, verifier, evaluation}` | `backend/runs/worker.py:77,151` |
| `profile_enrich` is a real graph node and is relayed | `agents/supervisor.py:207`, `backend/runs/worker.py:48` |

Nothing here was mid-build, so all three were done.

## 1. Editing a saved profile entry now reaches the right URL

`BuildProfile.jsx:110` — `` put(`/profile/entries/`, body) `` never interpolated
`entryId`, so every edit of a saved entry hit a route that does not exist and
405'd. One line. This was the item with real consequences beyond the UI: that
`PUT` is what **re-embeds** corrected text into the `profile` collection, so
while the URL was wrong a correction never reached retrieval and the superseded
text kept answering queries forever.

## 2. `stubs.js` is gone; the backend's own flag is used instead

The heuristics file had become actively wrong — `agents/matching.py` has been a
real brain since 2026-08-30, and the `matching` heuristic flagged any fit report
scoring above zero with an empty `matches` list, so **genuine** fit reports
rendered as "⚑ placeholder output".

- `applyEvent`'s `node_done` records `next.stubs[ev.node] = !!ev.stub`;
  `run.stubs` joins `artifacts` in the run fold (and in `IDLE`).
- `StatePanel` takes a `stubs` prop; `FinalOutput` takes a `stub` prop.
- `extractFinalArtifacts` now returns `stub` alongside `document`/`verifier`, so
  a past run opened from Runs labels the same way a live one does. `RunsView`
  spreads the result, so it picked this up with no change.
- `stubs.js` deleted. New `copy.js` holds `STUB_NOTE` — the documented home for
  plain-language strings, and where the gap-question wording should go next.

Side effect worth having: `verifier` is now labelled correctly, which the shape
heuristics could never detect. Old run logs have no `stub` field, so their
artifacts go unlabelled rather than mislabelled.

## 3. `profile_enrich` is visible

Both label maps predated the node, so `RunLog` printed the raw id, `AgentGraph`
drew 7 nodes for an 8-node run, and the artifact was fetched and stored but never
displayed.

- `AGENT_TITLES`: `profile_enrich: "Profile Update"`, positioned between
  `profile` and `matching` — order now matches `worker.py`'s `AGENTS` exactly.
- `CARD_TITLES`: `"Answers added to your profile"`.
- `renderArtifact`'s `profile` branch also takes `profile_enrich` (same
  `{evidence: [...]}` shape), with a different empty-state line: "nothing added —
  no answers were given at the evidence checkpoint" rather than "no evidence
  returned", because with no gap-answer form that empty result is the normal case.
- `PipelineView`'s subtitle now reads `{AGENTS.length} agents` instead of the
  hardcoded "seven", so it cannot go stale again.

`AgentGraph` needed no layout change — it is a flex row with `overflow-x-auto`.

## Verification status: **not run**

No build, no browser. There is no Node and no `node_modules` on this machine
(only Docker), and per standing instruction the frontend is not built or served
without asking — so this round is in exactly the state Round 3 warned about, and
the same caution applies: Round 3 found a syntax error that had survived two
sessions of review.

What was actually checked: every edited region re-read for JSX balance, and
`grep` confirms zero remaining references to `stubs.js` or `isStubArtifact`, and
that both `copy.js` importers resolve. That is import-level confidence only.

**The check to ask for:** `docker compose -f frontend/docker-compose.yml build
frontend`. Then, signed in, the one thing only a browser can show — start an
offline run and confirm the 8-node graph, a "Profile Update" card, and no
"placeholder output" chip on the Fit report.

## Still open, unchanged

- 🔴 **The gap-answer form does not exist** (item 1 of the 2026-08-31 list). This
  is the one that matters: `gap_questions` reach the browser, the answer route
  accepts `gap_answers`, and nothing renders an input, so `profile_enrich`
  no-ops on every UI run. Round 4 makes that *visible* — an empty "Answers added
  to your profile" card is now on screen — which is honest but not a fix.
- 🟠 **A gate can reopen with no signal** (item 3). The useful version needs a
  round number on the `gate_wait` emit in `backend/runs/worker.py`, which is
  outside this session's authority. A client-side count of repeat `gate_wait`s
  for the same node would work without any backend change.
- Features 5, 13, 14 (token management, per-identifier history, audit log) —
  still need `/api/auth/tokens*`. Feature 4 (vertical stepper), Feature 7 (design
  tokens), Feature 15a (confirm logout mid-run).

---

# Round 5 plan — the gap-answer form (gate 2), written 2026-09-24. **Not built.**

The frontend half of `context/bugs_audit_fixed.md` #29. It is the one
remaining piece keeping a UI run from doing what a CLI run already does. It is
listed as a next step in `context/context.md`'s header ("the gate-2
gap-interview form in the frontend"). This plan comes from reading the whole
round trip in the current code, not from the notes above.

## What happens today

1. The **Profile agent** grades each requirement `strong / partial / none`, and
   writes a follow-up question for every requirement that isn't `strong`
   (`agents/profile.py:86-91`). Offline, the fake model always produces two:
   `SQL` (partial) and `ETL pipelines` (none).
2. The graph pauses at **gate 2** (`gate2_evidence`). `utils/human_gate.py:54-59`
   puts those questions into the pause's payload, for gate 2 only.
3. **The backend relays them.** `backend/runs/worker.py:167-177` emits:
   ```json
   {"type": "gate_wait", "ts": "…", "node": "profile", "title": "Evidence review",
    "artifact_node": "profile",
    "gap_questions": [{"requirement": "SQL", "question": "Which projects did you…?"},
                      {"requirement": "ETL pipelines", "question": "Have you built…?"}]}
   ```
   `gap_questions` is `[]` on the other three gates, and missing entirely from
   run logs written before 2026-08-31.
4. **The frontend drops them.** `PipelineView.applyEvent`'s `gate_wait` case
   stores only `node`, `title` and `artifactNode` (`PipelineView.jsx:54`).
   `GateScreen` has one feedback box, and `answerGate` posts only
   `{decision, feedback}` (`PipelineView.jsx:108-110`).
5. So `state.gap_answers` stays `{}`. `enrich()` returns immediately
   (`agents/profile.py:100`), the "Profile Update" step finishes having done
   nothing, and the "Answers added to your profile" card shows its empty-state
   line on every UI run.
6. Meanwhile `renderArtifact`'s `profile` branch shows the same questions as
   `? …` lines on the gate-2 screen (`StatePanel.jsx:80-82`). The user is asked
   questions and given nowhere to answer them.

**The backend half is already in place**, and nothing below needs a backend
change:
- `POST /api/runs/{id}/gate` takes an optional
  `gap_answers: dict[str, str] = {}` (`backend/routes/runs.py:56`).
- The answer is passed through unchanged to the graph
  (`routes/runs.py:115-119` → `worker.py:223`).
- `gate_done` echoes `gap_answers` back (`worker.py:191`), so the event log
  records what was answered.

## The contract, exactly

**Request** (the only change on the wire is the new key):
```json
POST /api/runs/{run_id}/gate
{"decision": "approve", "feedback": "…", "gap_answers": {"SQL": "I wrote reporting queries at …"}}
```

**Key rule: use each question's `requirement` string exactly as received.**
Don't trim it, lowercase it, or build an id from it.
- `enrich()` looks up the question by exact string match
  (`agents/profile.py:105`). If a key doesn't match, the model is sent
  `QUESTION: No question found`.
- The saved block is named `gap_answer:{requirement}` (`profile.py:129`), so a
  changed key also produces a separate, near-duplicate entry.

**Values:** trim them, and leave out empty ones. An empty string is not a
"no" — just omit it. Send `{}` (or omit the key) when there's nothing to send.
Gates 1, 3 and 4 keep working unchanged, because the field defaults to empty.

## ⚠️ Three things this form must get right

**1. Never send answers with `reject`.** The graph stores `gap_answers` whatever
the decision (`human_gate.py:91-92`), and nothing clears them afterwards. A
reject sends the work back to Profile and reopens gate 2 with new questions.
If the rejected round's answers were already stored, they carry into the
next round: the user can approve the new round without typing anything, and
`enrich()` still saves the old answers to their profile. The CLI driver avoids
this by skipping the interview on reject (`scripts/run_gated_graph.py:56`).
Do the same: send `gap_answers: {}` on reject, and show a short note that
answers are dropped when you reject. Keep sending them on `edit`, as the CLI
does (for routing, `edit` behaves like approve; only `reject` loops back,
`agents/supervisor.py:116`).

**2. Demo mode writes to the real profile. Say so, and treat test runs with
care.** `save_gap_answers` (`learning/profile_store.py:37-83`) has no
offline check. In demo mode the fake model always returns the same polished
answer, *"Wrote SQL queries for business reporting."*, whatever the user
typed (`profile.py:38-43`). That answer is then:
- appended to `knowledge_base/profile/manual_entries.json`, and
- embedded into the real `profile` Chroma collection,

and future live runs can find it as evidence. So every demo run where anyone
answers even one question permanently adds a made-up line to the profile.
This isn't a frontend bug, and the fix belongs in `learning/`, outside the
frontend. But the form is what first makes it reachable from a browser, so:
- the helper text must say that answers are saved to the profile (true in
  both modes);
- until the `learning/` side is guarded, while testing the form in demo mode,
  check `manual_entries.json` afterwards and delete the test entries. There's
  no delete route and no vector delete yet (`context/bugs_audit_fixed.md`
  #30), so the Chroma copy can only be removed by rebuilding the index.

**3. Reset the answers when the gate reopens.** A rejected gate 2 comes back
with new questions from a re-run Profile agent, and they may be different
questions. Today `GateScreen` unmounts between gates (while `run.gate` is
`null`, `StatePanel` renders in its place), so its state resets anyway. Don't
rely on that: store `ev.ts` on `run.gate`, and render
`<GateScreen key={run.gate.ts} …/>` so every gate opening starts with an empty
form.

## Changes, file by file

**`PipelineView.jsx`** (3 small edits)
- `applyEvent`, `gate_wait`:
  `next.gate = { node, title, artifactNode, ts: ev.ts, gapQuestions: ev.gap_questions || [] }`.
  The `|| []` keeps old run logs replaying.
- `answerGate(decision, feedback, gapAnswers)` → post
  `{ decision, feedback, gap_answers: decision === "reject" ? {} : (gapAnswers || {}) }`.
  Enforce the reject rule here, at the one place a request is built, not only
  in the component.
- `<GateScreen key={run.gate.ts} … />`.

**`GateScreen.jsx`**
- `const [gapAnswers, setGapAnswers] = useState({})`, keyed by `requirement`.
- When `gate.gapQuestions?.length`, render one labelled `<textarea rows={2}>` per
  question, above the feedback box. Show the question text as the label, and
  the requirement as a small dim tag beside it (plain words such as "SQL", not
  an id).
- In `answer(decision)`, build
  `Object.fromEntries(Object.entries(gapAnswers).map(([k, v]) => [k, v.trim()]).filter(([, v]) => v))`
  and call `onAnswer(decision, feedback, cleaned)`.
- Give each input a `maxLength` of about 2000 (see the backend note below).
- Match the palette: the input styling of the existing feedback `textarea`,
  and the `#6ca0f5` blue the gate screen already uses for its heading.
- The `? …` lines inside `renderArtifact(profile)` now repeat the form's
  questions on the gate-2 screen. Either leave them (harmless, and they still
  help in the Drawer and on past runs), or pass a flag so `GateScreen` hides
  them. Your call; not required.

**`copy.js`** (it's there for exactly this, per its own header): add
- `GAP_HEADING = "A few things your profile doesn't cover yet"`
- `GAP_HELP = "Answer in your own words — anything left blank is skipped. Your answers are tidied up and saved to your profile, so future runs can use them."`
- `GAP_REJECT_NOTE = "Rejecting discards these answers."`

Avoid the words "gap", "evidence", "enrich" and "requirement" on screen, per
`context/design.md`'s no-jargon rule.

**`RunLog.jsx`** (optional, one line): in `gate_done`, append
`` ` · answered ${n} question(s)` `` when `Object.keys(ev.gap_answers || {}).length > 0`.
Past runs opened from Runs pick this up automatically, since `gate_done` is
already in the saved trail.

## Backend-side note (not blocking the form)

`gap_answers: dict[str, str]` has no size limit (`routes/runs.py:56`), unlike
`job_description`, which is capped at 20,000 characters (#37's reasoning). The
answers reach a prompt, a state snapshot, `manual_entries.json` and Chroma.
The `maxLength` above is courtesy only, not enforcement; the real cap belongs in
`backend/routes/runs.py`. Logged here so it isn't lost. It's a backend item.

> **✅ Landed 2026-10-10** (`backend/bugs.md` → "Round 8-10" #1). The field is
> now `dict[GapKey, GapText]` (key ≤200 chars, value ≤2000 chars, ≤20 keys),
> matching the `maxLength={2000}` courtesy this form already has, so a form
> that respects its own limits never hits the new 422. Two more checks
> landed alongside it that this round never needed, because it never sends
> either case: a 422 if `gap_answers` is non-empty at any gate but gate 2,
> and a 422 on any key that isn't one of *that* gate's own question keys. No
> frontend change needed to avoid either: this form already only sends
> `gap_answers` at gate 2, with real question keys. Today's fallback for any
> unexpected 422 here is just `err.message` shown inline with the buttons
> still live (item 3 above, before its own fix) — survivable, not pretty;
> not worth a special case for a path this form shouldn't be able to reach.

## How to verify (yours to run; per standing instruction, the assistant doesn't build or serve this)

1. `docker compose -f frontend/docker-compose.yml build frontend`, then sign in.
2. Start a **demo-mode** run and approve gate 1. Gate 2 should show two inputs:
   the SQL question and the ETL-pipelines question.
3. Answer only SQL, then approve. In the browser's network tab, the POST body
   should be `gap_answers: {"SQL": "…"}`, with no `ETL pipelines` key. Run
   Log: "you approved · answered 1 question". The "Answers added to your
   profile" card should now show *"Wrote SQL queries for business reporting."*
   (that's the fake output, not your text; see ⚠️ 2).
4. Start a second run, type answers at gate 2, and **Reject**. The POST body
   should have `gap_answers: {}`. Gate 2 should reopen with **empty** inputs.
   Approve without typing anything, and the Profile Update card should be
   empty.
5. Remove the test entry from `knowledge_base/profile/manual_entries.json`
   (⚠️ 2).
6. Open an old run (from before 2026-08-31) in Runs. It should replay with no
   errors and no form.

---

# Round 5 — audit of what Round 4 did not cover (2026-09-24)

Round 4 fixed three known items. This round re-read every file in
`frontend/src` against the **actual** backend rather than against these notes,
looking for defects not already recorded — including any Round 4 introduced.
Seven findings; four fixed, three left open below.

## ✅ 1. Every error message in the app rendered as raw JSON

`api.js` never parsed the response body — `new ApiError(res.status, await
res.text())` — so FastAPI's envelope reached the screen intact:

```
404 {"detail":"No file 'seed' in store 'profile'"}
422 {"detail":[{"type":"string_too_long","loc":["body","job_description"],…}]}
```

That is every error surface in the app: `Failed.jsx` (KB, Runs, Account,
Settings), `BuildProfile`'s save error, `AdminPanel`, `SearchPanel`, and
`LoginScreen.describe`'s fallback. Only `PipelineView`'s 403 escaped it, by
substituting its own sentence.

New `readDetail()` in `api.js` parses once: a string `detail` is used as-is, the
validation-array shape becomes `field: msg` (the last `loc` segment is the
useful half), and anything unparseable falls back to the raw text. `ApiError
.status` is untouched — `AuthContext`, `LoginScreen` and `PipelineView` all
branch on it.

The 2026-08-31 addendum's note on this was wrong in both directions; it has been
corrected in place above.

## ✅ 2. `BuildProfile` never loaded saved entries, so Round 4's fix was unreachable

`GET /api/profile/entries` has existed all along (`backend/routes/profile.py:100`)
and **nothing called it.** `saved` started empty on every mount, and `entryId` is
only ever set from that list — so the `PUT` path Round 4 had just repaired could
not be reached for anything saved before the last page load. Since that `PUT` is
what **re-embeds a correction into the `profile` collection**, a reload made your
own entries permanently uncorrectable.

`BuildProfile` now takes `active` (wired in `App.jsx` like `KnowledgeBase`) and
fetches through the existing `useFetch` hook. The fetched entries are **merged**
into `saved`, not assigned over it, so a slow response cannot drop an entry saved
while it was in flight. A failed load shows `Failed` rather than a silently empty
list.

Two labels went stale the moment the list stopped being session-scoped and were
corrected with it: "Saved this session" → "Your saved entries", and the preview
panel's "entries saved this session" → "entries in your profile".

Two latent throws came with reading records off disk instead of from this
session's own state, and are guarded: `editSaved` on an entry whose `section`
this build does not define was `SECTIONS[-1].questions` (a hard throw into the
ErrorBoundary), and the saved-row label assumed one of five known keys.

## ✅ 3. `DELIVERABLES.md` was stale on six user-facing claims

It is the "what there is to show" document, so being wrong there is worse than
being wrong in here:

| claimed | actually |
| --- | --- |
| "the **seven** agents … Job Analysis → … → Scoring" | eight — **Profile Update** sits between Profile Search and Matching |
| "**Rejecting stops the run.**" | reject sends the work back to the producing agent and **reopens the same checkpoint** |
| "the other **six** agents return example output" | three — `STUB_NODES` is `{document, verifier, evaluation}` |
| "The **five** screens" | seven — Account and Admin were never listed |
| "380 searchable entries" | the header counts them live; the prose no longer hardcodes a number |
| "No file in the main project was modified" | untrue for a long time; rewritten as what is still true of `frontend/` |

Also added: the gap-question form does not exist, so Profile Update has nothing
to add on a UI run. A demo that claims otherwise is worse than one that says so.

## ✅ 4. The pipeline graph could no longer stay aligned (Round 4 side effect)

`AgentGraph` drew the spokes and the nodes as two independent rows, only the
second scrollable. Nodes are `min-w-28` and grow with their titles, so the rows
drift apart as soon as one label is long — and at eight nodes the strip is wider
than the panel, so the node row scrolled while the fixed-width spoke row
stretched the panel around it.

Each spoke now lives in its node's own column inside one scroll container, so
alignment no longer depends on the two rows agreeing about width. The arrow
columns repeat the spoke's height so they centre on the nodes rather than on the
strip.

## 🟡 5. An errored run is labelled "stopped", exactly like a cancelled one — blocked

`registry.list_for` returns only `completed: any(type == "run_done")`, so
`RunsView.jsx` and `Account.jsx` cannot tell a crashed run from one superseded by
a newer one — both render "stopped" in red. The frontend has nothing to branch
on; the summary needs an `error`/`outcome` field. **Backend change, outside this
session's authority.** Flagged, not built.

## 🟡 6. A negative match score renders an invalid bar width

> **Fixed 2026-10-12 (Round 35):** `matchPct()` caps the score to 0–100.

`SearchPanel.jsx` sets `width: ${Math.round(h.score * 100)}%`. `score` is
`1 - cosine_distance` (`vectordb/store.py:94`) and Chroma's cosine distance goes
to 2, so a genuinely dissimilar hit yields a negative score: `width: "-40%"` is
ignored by CSS and the label reads "-40 match". Rare (it needs a hit more
opposite than orthogonal) and cosmetic. One-line clamp to `[0, 100]` whenever
you want it.

## 🟡 7. A revoked token can pass unnoticed in two places

> **Fixed 2026-10-14 (Round 42),** both places, as described below: a 401 in
> `refresh()` ends the session, and a dropped stream probes with `refresh()`.

Neither is a hole — the backend still refuses the call — but the user is not told
what happened:

- `AuthContext.refresh()` ends in `.catch(() => {})`, and `/auth/me` sits in
  `api.js`'s `NO_GLOBAL_401` set, so a 401 there is swallowed twice over. The
  runs-remaining counter just stops updating.
- `openEvents` uses `EventSource`, which never passes through `request()`, so an
  SSE 401 arrives as `onerror` and reads "lost the connection to this run"
  instead of ending the session.

The first is two lines. The second needs `onEnd` to learn *why* the stream
ended, which `EventSource` does not expose — it would mean a probe request on
failure.

## Checked and **not** a bug

Recorded so the coverage is legible, and so nobody re-derives it:

- `GateScreen`'s three decision strings match `GateAnswer.decision`'s
  `Literal["approve", "edit", "reject"]` exactly — no 422 risk there.
- `SearchPanel`'s three collection ids are all real (`vectordb/ingest.py:120`).
- `SettingsView` renders `AGENT_TITLES[agent] || agent`, so it picked up
  "Profile Update" for free and degrades gracefully for any future agent.
- `stub` is present on **every** `node_done` (`worker.py:151` — `False` for real
  agents, not absent) and `save_log` persists events wholesale, so Round 4's
  `extractFinalArtifacts` reads it correctly out of past runs too.
- Round 4's shared `profile` / `profile_enrich` render branch matches
  `agents/profile.py:144`: `enrich` returns `{"evidence": [...]}` with answers
  and `{"stage": ...}` without — exactly the empty-state path.
- An in-flight run is absent from `GET /runs` and its log 404s until it finishes
  (`save_log` runs `on_finish`). Backend-side by design; the frontend never asks
  for either mid-run.

## Verification status: **not run**

Same as Round 4, and the same caveat: no Node on this machine, and the frontend
is not built or served without asking. Finding 4 is reasoned from the CSS, not
observed in a browser.

**The check to ask for:** `docker compose -f frontend/docker-compose.yml build
frontend`, then, signed in:

1. Stop the bridge and open Knowledge Base — the red card should read a plain
   sentence, no braces.
2. Save a Build Profile entry, **reload the page**, and confirm it is still
   listed and still editable. The `updated` key appearing in
   `knowledge_base/profile/manual_entries.json` is what proves the `PUT` landed.
3. Start an offline run — the eight-node strip should scroll as one piece with
   every spoke over its own node.

---

# Round 6 — drift audit after the 2026-10 agent work (2026-10-07)

Nothing under `frontend/src` has changed since Round 5 (2026-09-24). The
**backend has**, substantially: commits `4ffe544` ("building agents complete,
except verifier") and `c63fa4f` ("changes in config + Infra") rewrote
`agents/document.py` (+334), `agents/matching.py` (+220), `agents/supervisor.py`
(+162), `agents/critic.py` (+79) and `state/state.py` (+181), and added
`agents/CV_Link.py` plus the whole `utils/cv_handling/` package.

This is an audit of what that did to the frontend's assumptions. Read against
the real code, not against these notes.

## The headline: the product changed shape

The run is no longer "write a CV from the knowledge base". It is **a tailoring
pass over an existing CV PDF**: `cv_link` parses `state.cv_path` into a `CVTree`
and matches every line to the profile records behind it, then `document` plans
edits per section, applies them to a copy of that tree, and renders markdown.

Two consequences, and only one of them is a bug:

- `Document(kind, content, unsupported_flags)` is **unchanged**, so
  `renderArtifact`'s `document` branch and `FinalOutput` still work exactly as
  before. Verified field by field in `state/state.py:161`.
- **The browser cannot choose the CV.** `backend/runs/worker.py:212-219` passes
  `cv_path=str(config.CV_DEFAULT_PATH)` with an explicit comment that it is
  "never taken from the request". `POST /api/runs` still accepts only
  `{job_description, mode}`. So every run started from the UI tailors
  `knowledge_base/input/CV_test.pdf` — which does exist, so runs are not broken,
  but "Start run" silently means "tailor the server's sample CV". The Pipeline
  screen says nothing about this. Fixing it properly needs an upload route
  first; that is a Backend ask.

## 1. 🔴 `cv_link` is a ninth pipeline node, and it is invisible twice over

The graph now runs nine nodes (`agents/supervisor.py:204-223`):

```
jd_analysis → profile → profile_enrich → matching → cv_link → document
            → critic → verifier → evaluation
```

`cv_link` is missing from **both** lists that matter:

- **`AGENTS` in `backend/runs/worker.py:45`** — and that list gates
  `_emit_routing`, which returns early for any node not in it. So the step emits
  **no `routing` and no `node_start`**. `_drain` is not gated the same way, so
  the `node_done` still arrives: the activity log shows a node *finishing* that
  never started.
- **`AGENT_TITLES` / `CARD_TITLES` in the frontend** — so `AgentGraph` draws
  eight nodes for a nine-node run, `RunLog` prints the raw id `cv_link
  finished`, `PipelineView`'s subtitle says "8 agents", and the artifact is
  stored in `run.artifacts.cv_link` and never displayed.

This is the `profile_enrich` drift of 2026-08-31 happening again, in the same
two places, and it is now the second occurrence — see `context.md` → Known sharp
edges for the standing check that would catch a third.

**The artifact needs a real renderer, not just a map entry.** `cv_link` returns
`{cv_tree, line_links}`: `cv_tree` is a recursively nested `CVNode` (every node
carries `text` *and* `raw_text`, plus `attrs` and `children`), and `line_links`
is one record per CV line (`{node_id, kind, section_type, text, status,
source_ids, score}`). `renderArtifact` has no branch for it, so the key/value
fallback would `JSON.stringify` an entire parsed CV onto one line. The useful
card is a count, not a dump — something like "N lines, M linked to evidence, K
unmatched", with the per-line table behind the existing `detail →` drawer.

Worth knowing before building it: this artifact is also by far the largest thing
the SSE stream now carries, and `RunLog` keeps every event for the session.

**Split of work:** adding `"cv_link"` to `worker.AGENTS` is the backend's
(one line, and it is what restores `routing`/`node_start`); the two map entries
and the renderer branch are this folder's. The backend half is written up as
item 1 of `backend/bugs.md` → 2026-10-08.

## 2. 🔴 `document` is real now, and the UI calls it a placeholder

`agents/document.py` is a full writer — plan → per-section packets → LLM edit
sets → `_guard_edits` → `apply_edits` → `render_markdown`. `STUB_NODES` in
`backend/runs/worker.py:77` still reads `{"document", "verifier", "evaluation"}`.

So `node_done` carries `stub: true` for `document`, and `StatePanel` and
`FinalOutput` stamp **"placeholder output — this agent is not implemented
yet"** on the genuine, tailored CV. That is the exact failure that got
`stubs.js` deleted on 2026-09-24, arriving this time from the backend table
instead of a frontend heuristic.

Confirmed still placeholders, both returning a hardcoded result with a `TODO`
docstring: `verifier` (`PASS`, so the loop-back stays off) and `evaluation`
(empty `EvalRecord`). `critic` is real and was already correctly excluded.

**Fix is one entry out of one set, backend-side.** The frontend needs no change
and **must not** add a compensating heuristic — that is precisely how `stubs.js`
began.

**Also stale because of this:** `DELIVERABLES.md` was corrected on 2026-09-24 to
say three agents are placeholders, naming Writer among them. It is wrong again —
Writer is real, and the agent list there is still eight-with-Profile-Update
rather than nine-with-CV-Link. Not touched in this round (it was not in scope);
it needs the same two corrections it got last time.

## 3. 🟠 Gate 3 now opens one node later than its own label says

`STAGE_GATE` (`agents/supervisor.py:51`) is keyed on *the stage about to run* —
"pause before entering this stage". `gate3_fit` is keyed on `Stage.DOCUMENT`,
and `cv_link` now sits between `matching` and `document`, so gate 3 opens
**after `cv_link`**. `worker.GATES["gate3_fit"]["after"]` still says
`"matching"`.

Contained, and nothing to fix in this folder:

- the review screen is correct — it renders `artifact_node`, which is still
  `matching`, which is still the thing being approved;
- `GateScreen`'s `showsVerifierToo` stays correctly `false` for gate 3 and
  `true` for gate 4 (verified: gate 4 is still `after: verifier`,
  `artifact_node: document`);
- the only visible effect is that the pulsing "waiting" dot sits on Matching
  while the run is actually parked one node later.

Worth correcting in `worker.GATES` whenever the backend touches that table, but
it is a label, not a defect.

## 4. 🟠 `document`'s event payload grew by an order of magnitude

`document.node` now returns `{document, document_patches, document_plan,
document_plan_key, evidence}` and the worker puts every non-`messages` field in
the artifact. Rendering is unaffected — the branch matches on `a.document` and
ignores the rest — but each `node_done` for `document` now carries the full edit
plan, the full patch set and any evidence blocks it fetched, and the run log
persists all of it.

No action unless the stream gets slow. Noted because the obvious debugging
instinct — "why is this run log 2MB" — now has an answer.

## Verified unchanged

Checked field by field so nobody re-derives it:

- `Document`, `FitReport`, `ProfileBlock`, `GapQuestion`, `RequirementAssessment`
  — every field the frontend renders is intact (`state/state.py:75-165`).
  `matching.py` grew by 220 lines without changing `FitReport`'s shape.
- All four gate `title` strings, all four `after`/`artifact_node` pairs except
  the gate-3 position noted above, and `gate_wait`'s `gap_questions` (still
  `[{requirement, question}]`, still gate 2 only — `utils/human_gate.py:58`).
- `GateAnswer.decision` is still `Literal["approve", "edit", "reject"]`, which
  is still exactly what `GateScreen` sends.
- `config.CV_DEFAULT_PATH` resolves to `knowledge_base/input/CV_test.pdf`, and
  that file is present — so `cv_link` and `document`, both of which raise
  without it, do not break UI runs.
- Reject still loops back rather than ending the run (`decide()` →
  `GATE_PRODUCER`), and it is still capped by `max_revisions`.

## Still open from earlier rounds

Unchanged and still accurate:

- 🔴 **The gate-2 gap-answer form** (2026-08-31, item 1) — still the largest
  open frontend item. `gap_questions` arrive, `gap_answers` is accepted, nothing
  renders an input, so `profile_enrich` still has nothing to add on a UI run.
- 🟠 **A reopened gate gives no "revised version" signal** (2026-08-31, item 3).
  Note the backend *does* now have what it needs: `decide()` compares
  `latest.revision` against `state.revision_count` to decide a gate must reopen,
  so the round number exists in state — it is simply not on the `gate_wait`
  event.
- 🟡 Round 5's three: an errored run labelled "stopped" (needs a backend field),
  a negative match score rendering an invalid bar width, and a revoked token
  passing unnoticed in `refresh()` and over SSE.

## Verification status: **nothing run, and nothing changed**

This round edited only `context.md` and this file. No code was touched, so there
is nothing new to build — the last code change was Round 5 (2026-09-24), still
itself unbuilt. The standing rule holds: no Node on this machine, and the
frontend is not built or served without asking.

Everything above was read out of the Python source. The one thing a browser
would add is confirming that `cv_link`'s `node_done` really does arrive with no
`node_start` before it, which is visible in the activity log of any run.


---

# Round 7 — scoping from the backend's October audit: auth, data leaks, run races (2026-10-08)

Written from a read-only backend scoping pass (`backend/context.md`, "⧉ OCTOBER
SCOPING PASS"), not from running anything. Everything below is a frontend
consequence of a backend-side gap — the fix for each is mostly backend work,
but each one changes how `frontend/src` should behave *today*, or what it needs
to be ready to render *soon*. Round 6 already covers the `cv_link`/`document`/
gate-3 drift; this round doesn't repeat it.

## 1. 🟠 Two routes already show one user another user's data — relevant to `BuildProfile.jsx` right now

`GET /profile/entries` and `PUT /profile/entries/{id}` have no owner check
server-side (`backend/routes/profile.py:100-136`). The moment a second token
exists, `BuildProfile.jsx` will render entries nobody at this keyboard wrote —
including gap-interview rows with their raw interview answer — as if they were
the signed-in user's own, and editing one silently rewrites *someone else's*
evidence in the shared retrieval index. This isn't a rendering bug to fix here;
it needs an `owner` field and a 403 on the backend first. Noted because it's
real today with just two tokens, not a Stage-0-only concern, and because once
it's fixed server-side (403 on someone else's `id`), `BuildProfile.jsx`'s
`save()` needs to treat that 403 the same way it already treats a 405 —
inline error, not a thrown rejection.

`GET /api/kb/profile/manual_entries` and `POST /api/search {collection:
"profile"}` have the same gap, reachable from `KnowledgeBase.jsx` and
`SearchPanel.jsx` respectively. No frontend change needed for these two today
— just worth knowing that "search profile" and "browse KB → profile" can both
surface another user's gap answers until the backend scopes them.

## 2. ✅ A double-clicked Start can spend a new user's entire allowance — **frontend half fixed 2026-10-09 (Round 10)**

`PipelineView.jsx`'s Start button has no in-flight guard
(`onClick={start}` / `disabled={!jd.trim()}` only — `PipelineView.jsx:139-145`),
and the backend has nothing to deduplicate a repeat `POST /runs` either (each
call consumes one run before checking for a previous in-flight run to
supersede). Two fast clicks on a fresh token with the default allowance of 2
spends both runs on what the user experiences as one click.

**Frontend fix, independent of the backend side:**
```js
const start = async () => {
  if (startingRef.current) return;
  startingRef.current = true;
  ...
  finally { startingRef.current = false; }
};
```
or simpler, disable the button for the duration of the `post("/runs", …)` call
(a `starting` state, same pattern the gate buttons already use via `sending`).
Also close any previous `EventSource` before opening a new one —
`closeRef.current` is currently overwritten without being called
(`PipelineView.jsx:98-104`), so a double-start folds two runs' events into one
view with no error.

The backend side (an idempotency key) is tracked in `backend/context.md`;
once it lands, send `crypto.randomUUID()` as `client_request_id` in the `POST
/runs` body so a retried request can't double-spend even without the button
guard.

## 3. 🟡 A paused run is invisible after a refresh or a backend restart — today, not just under Stage 0

The run id lives only in `PipelineView`'s React state
(`runIdRef.current` — `PipelineView.jsx:80`), and the backend only writes a
run's log file when it *finishes* (`backend/runs/worker.py`'s `finally`). So:
a run parked at any gate, then a page refresh, has no way back — there is
nothing to look it up by, and `GET /api/runs` won't list it because its log
was never written. The existing `streamLost` message ("lost the connection to
this run — reopen it from Runs once it finishes") is accurate for a run that
*will* finish, but not for one parked at a gate waiting on input that was lost
with the refresh — it won't appear in Runs until someone answers a gate that
no browser tab is showing any more.

No frontend fix proposed here — the real fix is backend-side (persist the log
at gate time, not only at the end; tracked in `backend/context.md` §3). Noted
so the `streamLost` copy isn't mistaken for already covering this case, and as
a flag for whenever a "resume a run" affordance gets built: it needs a `GET
/api/runs/{id}` that returns the *current* gate/status for an in-flight run,
which doesn't exist yet either.

## 4. 🟡 Advance notice: three more gates are coming, and `GateScreen` will need a gate identifier

Per the Stage 0 plan, the Profile agent will eventually pause at an intake
gate and two confirm gates, in addition to today's four. Two things worth
knowing before that lands, on top of everything "Round 5 plan" already says
about the gap-answer form:

- **These will likely arrive as a `gate` field on `gate_wait`/`gate_done`**
  (not yet on the wire — flagged as needed in `backend/context.md` §2), because
  the intake gate and today's gate 2 both fire at the same position
  (`after: "profile"`) and can only be told apart by title string otherwise.
  When it arrives, `PipelineView.applyEvent`'s `gate_wait` case should store
  it (`next.gate.gate = ev.gate`) and `answerGate` should send it back
  unchanged — the backend will reject a mismatched gate id with 409, which is
  the signal a stale form submission is being caught.
- **A confirm gate's payload will be a change set to accept/edit/reject per
  item**, not a feedback box. This is a materially different UI shape from the
  existing `GateScreen` (which is one artifact + one feedback textarea) —
  worth designing as its own gate-type branch (`gate.kind === "confirm"`) rather
  than trying to generalize the existing approve/edit/reject buttons onto it,
  since "edit" here means "accept some of N proposed changes," not "the whole
  thing needs revision."

Not actionable yet — the agents/backend side isn't built. Written down so the
next round building the intake/confirm UI doesn't have to re-derive the gate-id
problem from scratch.

## 5. 🟡 Which CV a run tailors is not shown anywhere on the Pipeline screen

Today every run patches one fixed server-side sample CV
(`config.CV_DEFAULT_PATH`) — there's no upload route, and `RunRequest` has no
field for one. `PipelineView.jsx`'s idle screen shows the job-description box
and the mode toggle, with nothing saying which CV the run will use or that it's
a shared sample rather than the signed-in user's own. This is an open product
decision on the backend side (upload vs. a different CV source vs. keep the
shared sample and say so — `backend/context.md` §4), not a frontend bug. Flagging
it here because whichever way it's decided, the idle screen's copy needs a line
added — either "using the sample CV" (if nothing changes) or a CV name/upload
affordance (if upload is built).

## Verification status: **nothing run, nothing changed**

This round, like Round 6, only edits this file. The underlying facts come from
reading `backend/routes/*.py`, `backend/runs/{registry,worker}.py`,
`backend/auth/store.py` and `frontend/src/components/{PipelineView,
BuildProfile}.jsx` — not from a live request, a build, or a browser. Standing
rule still applies: no frontend build or serve without asking first.

---

# Round 8 — the gate-2 answer form, built (2026-10-09)

Builds "Round 5 plan — the gap-answer form" above. Frontend only. Before writing
any code, the backend contract was re-checked in source and is unchanged:
`GateAnswer.gap_answers: dict[str, str] = {}` (`backend/routes/runs.py:56`),
`gate_wait` carries `gap_questions` and `gate_done` echoes `gap_answers`
(`backend/runs/worker.py:180,195`), and `enrich()` matches an answer to its
question by exact `requirement` string (`agents/profile.py:105`).

## What changed

- **`PipelineView.jsx`**
  - `gate_wait` stores `ts` and `gapQuestions` (`|| []`, so old logs replay).
  - `answerGate(decision, feedback, gapAnswers)` sends `gap_answers`, and forces
    `{}` on `reject`. This is the one place a request is built, so the rule
    holds even if the component changes.
  - `<GateScreen key={run.gate.ts} …>`.
  - The run remembers its own `mode`, so the gate knows it is in demo mode.
- **`GateScreen.jsx`**: when the gate has questions, one labelled 2-row textarea
  per question, keyed by `requirement` exactly as received, with the requirement
  shown as a dim tag. Values are trimmed and blanks dropped before sending.
  `maxLength` is 2000, as a courtesy only: the backend still has no cap.
- **`copy.js`**: `GAP_HEADING`, `GAP_HELP`, `GAP_REJECT_NOTE`, plus `GAP_DEMO_NOTE`.
- **`RunLog.jsx`**: `gate_done` appends "· answered N question(s)". Past runs
  opened from Runs get this too.

## Where this differs from the Round 5 plan

- **A demo-mode warning was added (`GAP_DEMO_NOTE`, amber).** In demo mode the
  stand-in model returns one fixed SQL answer whatever was typed
  (`agents/profile.py:38-43`), and `save_gap_answers` writes it to the real
  profile. Without the note, a tester types one answer and sees a different one
  appear, which reads as a bug. ⚠️ 2 of the plan still applies: clean
  `manual_entries.json` after demo testing. The real guard belongs in `learning/`.
- **One box per requirement, first question wins.** If the profile agent ever
  emits two questions for the same requirement, two boxes would share one answer
  key. `enrich()` only ever uses the first question per requirement, so the form
  does the same.
- **The `? …` question lines in `renderArtifact(profile)` were left in place**
  (the plan left this to us). On the gate-2 screen they repeat just above the
  form. They still help in the Drawer and on past runs.
- **The free "add or correct anything" box (DELIVERABLES §18) was not built.**
  `GateAnswer` has no `free_text` field yet, and FastAPI ignores unknown body
  keys. A box today would accept text and silently drop it. Build it when §17
  adds the field.

## Verification status: **not run**

No build and no browser: there is no Node on this machine, and the frontend is
not built or served without asking. What was checked: every edited region
re-read, brackets balanced in all four files, and diffs against pre-edit copies.
That is not a build. Round 3 found a syntax error that had survived two sessions
of review.

**The check to ask for** is the Round 5 plan's "How to verify" list, unchanged:
`docker compose -f frontend/docker-compose.yml build frontend`, then in demo mode
answer SQL only and confirm the request body is `{"SQL": "…"}`. Then reject with
answers typed and confirm `gap_answers: {}` and an empty form when the gate
reopens. Finally, delete the test entry from `manual_entries.json`.

---

# Round 9 — `cv_link` made visible, frontend half (2026-10-09)

Fixes the frontend half of Round 6, item 1. Frontend only. The artifact shape
was read from source rather than from the Round 6 notes:
- `agents/CV_Link.py:46` returns `{cv_tree, line_links, stage}`;
- `LineLink` is `{node_id, kind, section_type, text, status, source_ids, score}`,
  where `status` is `matched` / `partial` / `unmatched` (`state/state.py:330,359`);
- `_drain` sends the step's return value as the artifact
  (`backend/runs/worker.py:154`).

## What changed

- **`AgentGraph.jsx`**: `cv_link: "CV Reader"`, between Matching and Writer. The
  strip now draws nine steps. `RunLog` prints "CV Reader finished" instead of the
  raw id. The Pipeline subtitle counts `AGENTS`, so it now says 9.
- **`StatePanel.jsx`**:
  - `CARD_TITLES` gains "Your CV, checked against your profile".
  - A `cv_link` branch in `renderArtifact`. The card shows the file name, lines
    checked, and "backed by profile: N yes · N partly · N no".
  - `renderArtifact` takes an optional third argument, `{ detail }`. Only the
    drawer passes it. With it set, the branch also lists every line under the
    CV's own section headings (taken from `cv_tree.root.children[].title`).
    Each line gets a backed / partly / not found chip, with bullets indented and
    the profile record ids it was linked to shown dimmed, as the profile branch
    already does.
- **`PipelineView.jsx`**:
  - The drawer passes `{ detail: true }`.
  - `applyEvent` keeps the earlier `cv_link` artifact when a new one has no
    `line_links`. That happens after a rejected fit review: Matching re-runs,
    `cv_link` runs again, sees the same CV already read (`CV_Link.py:37-38`), and
    returns only `{stage}`. Without this rule the card would go blank. The
    earlier read is still the run's, because the graph state was not changed.

## ~~What still looks odd, and is the backend's half~~ — corrected 2026-10-09

> **The first two points below were wrong when written.** They were taken from
> this file's Round 6 notes instead of from the code. `backend/bugs.md` →
> 2026-10-08 had already fixed them that same day, and the code confirms it:
> `cv_link` is in `worker.AGENTS` (`:51`), and gate 3 is `after: "cv_link"`
> (`:69`). So CV Reader does get `routing` and `node_start`, and the gate-3
> waiting dot sits on CV Reader. `STUB_NODES` is also `{"verifier",
> "evaluation"}`, so the Writer's CV is no longer labelled a placeholder.
>
> ~~No "working" state and no routing line for CV Reader.~~ ~~At the fit review,
> CV Reader shows complete while Matching shows waiting.~~

- **The artifact is still huge on the wire.** The card shows a few counts, but
  the full `cv_tree` is still in the event, and `RunLog` keeps every event for
  the session (Round 6, item 4). Now asked of the backend, with a proposed
  shape: `backend/bugs.md` → 2026-10-09, item 5.

  > **✅ Partly fixed 2026-10-10** — the privacy half, not the size half.
  > `worker.py`'s `_drain` now strips the header section (name, email,
  > phone) and `raw_text` at every node before the `cv_link` artifact is
  > emitted or persisted. **No wire-shape change** on purpose: `cv_tree`
  > is still `{source_file, root: {...}}`, and this card reads only
  > `node_id`/`title` off `root.children` (never `text`/`raw_text` at any
  > depth), so nothing here needed editing and nothing breaks on an old
  > log replayed against the new code. **Still open, and still a decision
  > for the user, not either lane to pick alone:** the tree is still large
  > (per-node structure, just with blanked `raw_text`), and `line_links`'
  > per-line text is untouched — moving either behind an owner-checked
  > route is the real size fix, deferred in `backend/bugs.md`'s own words
  > as "a decision that isn't the frontend's to make."

## ✅ ~~Open, frontend~~: the fit review shows an empty "Fact check" block — **fixed 2026-10-09 (Round 14)**

Found while correcting the above, and caused by the backend's gate-3 move, not by
this round. `GateScreen` decides "this is the final gate, show the fact check
underneath" from `artifactNode !== gate.node`. That was true only of gate 4
(`document` vs `verifier`) until gate 3 moved. Gate 3 is now `matching` vs
`cv_link`, so the fit review renders "Fact check · output of CV Reader — no
output yet" under the fit report.

The fix is one line in `GateScreen.jsx`: `const showsVerifierToo = gate.node
=== "verifier";`. Once the backend sends a gate name (`backend/bugs.md` →
2026-10-09, item 3), switch it to `gate.gate === "gate4_document"`. Not fixed
here: the request that found it was documentation only.

## Verification status: **not run**

Same caveat as Round 8: no build and no browser, because there is no Node here
and the frontend is not built or served without asking. What was checked: every
edited region re-read, brackets balanced, and diffs against pre-edit copies.

**The check to ask for:** `docker compose -f frontend/docker-compose.yml build
frontend`. Then, signed in, start a demo-mode run and confirm:
- the strip shows nine steps with CV Reader between Matching and Writer;
- after the fit review, a "Your CV, checked against your profile" card shows
  counts;
- CV Reader's `detail →` lists the CV's lines under its own section headings.

Then reject the fit review once. When it reopens and is approved, the CV card
should still show the same counts, not "no CV lines were checked".

---

# Round 10 — one click, one run (2026-10-09)

Fixes the frontend half of Round 7, item 2. Frontend only, `PipelineView.jsx`
only. Re-checked in source first: `start_run` calls `consume_run` on every
`POST /runs` (`backend/routes/runs.py:66`), and `RunRequest` has no idempotency
field.

## What changed

- **`start()` allows only one request in flight.**
  - A `startingRef` guard returns early on any repeat call. It is a ref, not
    state, so the check never reads a stale render.
  - A `starting` state disables Start and relabels it "starting…".
  - Both reset in a `finally`, so a failed start (403, 422, unreachable) leaves
    the button usable with its error shown, as before.
- **Any previous stream is closed before a new one opens.**
  - `closeRef.current` used to be overwritten without being called. A second
    run's `EventSource` then shared the view with the first, and the first's
    `run_stopped` (it had been superseded) set `done` on a run still going.
  - With the guard in place this shouldn't be reachable from the idle screen.
    Closing first is free, and it keeps one stream per view as a rule rather
    than a coincidence.

## Still open, backend side

Only the button is guarded. Two tabs, a script, or a retried request can still
spend two runs. The real fix is an idempotency key on `POST /runs`
(`backend/context.md`). When it lands, send `crypto.randomUUID()` as
`client_request_id` from `start()`. Don't send it before then: it would be
ignored.

> **✅ Landed 2026-10-10** (`backend/bugs.md` → "Round 8-10" #4). `RunRequest`
> now accepts optional `client_request_id: str | None` (8–64 chars), and
> `start_run` + `registry.owner_lock`/`seen`/`remember` serialise this owner's
> starts and hand back the same `run_id` for a repeat id — fixing the
> underlying race (`registry.start` could previously let two concurrent
> starts from one owner both pass the "no active run" check), not just the
> UI symptom this round guarded against. **Needed now:** send
> `crypto.randomUUID()` once per Start attempt as `client_request_id` — it's
> accepted and ignored if omitted, but the dedup (and the one real benefit
> left after the button guard: surviving a retried request without a double
> charge) only kicks in once the frontend sends it.
>
> **✅ Sent since 2026-10-10 (Round 29),** once per start rather than per
> attempt; see Round 29 for why.

## Verification status: **not run**

Same caveat as Rounds 8–9: no build and no browser. Checked by re-reading the
edit, a diff against the pre-edit copy, and balanced brackets.

**The check to ask for:** build, sign in with a **user** token (admin is never
charged, so it can't show the bug), and double-click Start. You should see
exactly one `POST /api/runs` in the network tab, and the header's
runs-remaining count should drop by one, not two.

---

# Round 11 — what the frontend needs for a user-supplied CV (2026-10-09). **Frontend half written → Round 12.**

Scoping only. This file is edited and nothing else. It turns the "Your CV" addendum
at the bottom of `frontend/design.md` into a frontend task list, and closes Round 7
item 5 ("which CV a run tailors is not shown") as a decision: **upload is the
direction**, so the copy-only alternative ("using the sample CV") is dropped.

Re-checked in source before writing:
- `POST /api/runs` still takes only `{job_description, mode, pace_seconds}`, and the
  worker still passes `config.CV_DEFAULT_PATH` (the sample `CV_test.pdf`) to every run.
- There is no upload route, no file input and no CV state anywhere in
  `frontend/src`. The only CV mention is the "CV Reader" label in `AgentGraph.jsx`.
- `api.js`'s `request()` sends `application/json` whenever there is a body
  (`api.js:60`) and has no way to send a file.
- `frontend/src/` has no `stubs.js`, though `design.md` refers to one.
- `frontend/nginx.conf` sets no `client_max_body_size`, and `python-multipart` is not
  in `requirements.txt`. Both are listed below as backend-side blockers, not frontend.

## Needed from the frontend

### 1. 🔴 A way to upload a CV (nothing exists)

Without it every browser run tailors the same sample CV, and Stage 0's exit check
("downloads a CV built from their own profile") cannot be met.

- **`api.js`: an `upload(path, file)` sibling to `request()`.**
  - Sends `FormData` with one field, `file`.
  - Must **not** set `content-type`: the browser adds the multipart boundary.
  - Keeps the `authorization` header and the existing `ApiError` / 401 handling.
  - Needs upload progress, so it probably uses `XMLHttpRequest` rather than `fetch`.
    Decide when writing it.
- **A CV strip on the Pipeline idle screen**, above the job-description box
  (`PipelineView.jsx`). One line, always visible before a run:
  - with a CV: `CV · <filename> · <n> pages · uploaded <date>   [Replace]`
  - without: `CV · none yet   [Upload PDF]`, **Start run disabled** with the reason
    inline ("Add your CV to start a run")
  - drag-and-drop onto the strip as well as the file picker. No modal, no wizard.
- **Client-side rejects before anything is sent:** not a PDF, over 5 MB. Specific
  reason in the strip.
- **States:** idle, uploading (a thin bytes-based progress bar), reading (server is
  parsing), read preview, ready, failed. On failure the previous CV is kept and shown.
- **A "What we read" preview**, an inline expandable panel before the CV is accepted:
  sections found, each with entry and line counts, collapsed by default; expanding
  shows entries and lines as plain read-only text (the `RecordCard` look, not a JSON
  tree); parser warnings in plain words; buttons **Use this CV** / **Cancel**.
  Inline editing of what was read is out of scope.
- **Replace** goes through the same flow. The old CV stays current until **Use this
  CV**. A run already going keeps the CV it started with.
- **Account.jsx: a "Your CV" row** with the same details, plus Replace and Delete.
  Delete confirms inline, never in a modal.

### 2. 🟠 Show which CV a run used

Three places, so an old run stays readable after the CV is replaced:
- the run header in `PipelineView.jsx`;
- the gate 3 and gate 4 review screens (`GateScreen.jsx`): "tailoring: <filename>";
- `FinalOutput.jsx`: "tailored from <filename>, uploaded <date>".

Also the file name on rows in `RunsView.jsx` and `RunLog.jsx`. This needs the run
record and `run_started` to carry `cv: {id, filename}`. **Never** CV text.

### 3. 🟠 Specific error text per server status

Never a generic "upload failed".

| Status | UI text |
|---|---|
| 413 | "This PDF is larger than 5 MB." |
| 415 | "This file isn't a PDF." |
| 422 `no_text` | "This PDF has no selectable text. It looks scanned. Export it from your editor as a text PDF." |
| 422 `no_sections` | "We couldn't find CV sections (Experience, Projects, Skills…) in this PDF." |
| 422 `too_many_pages` | "Keep your CV to 4 pages or fewer." |
| 409 on `POST /runs` | Start stays disabled; shown only if a stale screen got past the guard |
| 403 | the existing 403 handling. **Never treat it as 401**, or the user is logged out |

### 4. 🟡 Say plainly when a first run will barely change the CV

A new user with an empty profile gets every CV line back unmatched, so Document has
no evidence to edit with and the CV comes back mostly unchanged. At gate 4, the UI
should say so instead of looking broken. **Blocked on the backend exposing the
unmatched count.**

### 5. 🟡 Stub data so the screens can be built first

Add a stub `CvSummary` and `CvPreview` (shapes below) in `frontend/src`, as the
`design.md` addendum asks, so the strip and preview can be built before the routes land.

## Contract the screens assume (backend half, from `design.md`)

| Route | Response |
|---|---|
| `POST /api/profile/cv` (multipart, field `file`) | `201 {cv: CvSummary, preview: CvPreview}`, stored as **pending** |
| `POST /api/profile/cv/{cv_id}/confirm` | `200 {cv: CvSummary}`, makes it current |
| `DELETE /api/profile/cv/{cv_id}` | `204` |
| `GET /api/profile/cv` | `{cv: CvSummary \| null}` |
| `POST /api/runs` | unchanged body; the server resolves the caller's current CV; `409` if none, **before** `consume_run` so no allowance is spent |

- `CvSummary = {id, filename, size_bytes, pages, uploaded_at}`
- `CvPreview = {sections: [{type, title, entries: [{header, lines: [str]}]}], warnings: [str]}`

## Blockers that are not the frontend's

- **No upload route exists** (above). The whole screen is stub-only until it lands.
- **`python-multipart` is not in `requirements.txt`** (FastAPI file uploads need it;
  it is installed in `.venv` only).
- **nginx's default 1 MB body limit** would reject a 1–5 MB PDF with an nginx error
  page, not the API's JSON. `frontend/nginx.conf` needs `client_max_body_size 6m;`
  on `location /api/`.
- **The CV is linked against the shared synthetic `profile` collection**
  (`agents/CV_Link.py`), not the user's own. A real user's CV would be linked to the
  synthetic records until profile-scoped linking lands (Stage 0 §13).

## Verification status: **not run, nothing built**

Only this file changed. Facts come from reading `frontend/src/api.js`,
`frontend/src/components/`, `frontend/nginx.conf`, `requirements.txt`,
`backend/runs/worker.py` and `frontend/design.md`. No build, no browser. Standing
rule: no frontend build or serve without asking first.

---

# Round 12 — "Your CV", frontend half, built from Round 11 (2026-10-09)

Frontend only. It builds Round 11's list against the contract in
`design.md`'s "Your CV" addendum. The backend routes still don't exist (checked:
no upload code in `backend/`, and `GET /api/profile/cv` is a plain 404 today). So
everything is written to **work against today's backend and switch over by
itself** when the routes land.

**Decision taken:** D-CV2 as recommended. A user with no CV can't start a run;
the admin may run on the shared sample, labelled. D-CV1 (upload in Stage 0)
is treated as yes, since this is that work.

## What changed

- **`api.js`**
  - `upload(path, file, onProgress)`, multipart field `file`. It uses
    `XMLHttpRequest` because `fetch` can't report upload progress. It sets no
    content-type, so the browser adds the boundary. Errors become the same
    `ApiError` with `readDetail`, network failure is status 0, and a 401 fires
    the central logout.
  - `del(path)`.
  - `request()` returns `null` on 204 instead of failing to parse an empty body.
- **`CvContext.jsx`** (new): the caller's current CV, shared because Pipeline and
  Account must agree. It is keyed by signed-in user in `App.jsx`, so a new user
  starts fresh. `status` is one of:
  - `loading`;
  - `ready` (`cv` or `null`);
  - `unavailable`: GET returned 404/405, meaning the route isn't deployed (once
    it exists, "no CV" is `{cv: null}`);
  - `failed`: unreachable or 5xx. It shows a retry and does **not** block Start,
    because the server still decides.
- **`CvStrip.jsx`** (new): the one-line `CV · file · N pages · uploaded 9 Oct
  [Replace]` strip.
  - Picker plus drag-and-drop.
  - Client-side rejects before anything is sent: over 5 MB, or not starting with
    `%PDF-` (magic bytes, whatever the extension).
  - States: uploading (progress % and a thin bar) → reading → preview → saving →
    ready. A failure leaves the old CV current and shows one specific sentence
    from the error table.
  - Account adds Delete, with an inline confirm and no modal.
  - Drops onto the strip are always swallowed. Otherwise the browser would open
    the PDF in the tab and navigate away from a live run.
  - An unconfirmed upload is deleted server-side on Cancel, on picking another
    file, and when the strip unmounts (starting a run unmounts the Pipeline
    one). These deletes are fire-and-forget.
- **`CvPreview.jsx`** (new): "What we read".
  - Parser warnings in amber.
  - One collapsed `<details>` per section, "Projects · 3 entries · 9 lines".
  - Expanded, each entry shows its header and lines as plain text.
  - **Use this CV** / **Cancel**. Read-only, as specified.
- **`PipelineView.jsx`**
  - The strip sits above the job description.
  - Start is disabled with "Add your CV to start a run." for a user with no CV.
  - A 409 from `POST /runs` shows the same sentence and re-checks the CV.
  - The run screen gets a `tailoring: <file>` line above the graph. It reads the
    server's `cv` from the `POST /runs` reply or a `run_started` event. While the
    routes don't exist it shows "sample CV (not yours)".
  - `applyEvent` handles `run_started`.
- **`Account.jsx`**: a "Your CV" block (the strip, with Delete).
- **`RunsView.jsx`**: `· <file>` after the job description, when the run summary
  carries `cv`.
- **`RunLog.jsx`**: "run started — tailoring <file>".
- **`copy.js`**: every CV string, including the error table verbatim.
- **`nginx.conf`**: `client_max_body_size 6m` on `/api/`. Round 11 listed this as
  a backend blocker, but the file is this folder's, so it's done here.

## Round 11 items, by status

| # | Item | Status |
|---|---|---|
| 1 | Upload, strip, client rejects, states, preview, replace, Account row | written |
| 2 | Which CV a run used | written, partly. The run header line covers the gate screens and the final output, because it sits above them, so `GateScreen` / `FinalOutput` were not touched (another session is editing both). Runs rows and the log line show the file **only once the backend sends `cv`** |
| 3 | Error text per status | written. 413/415 by status. 422 maps when `no_text` / `no_sections` / `too_many_pages` appears in the detail; any other detail is shown as sent |
| 4 | "First run will barely change your CV" | still blocked on an unmatched count from the backend |
| 5 | Stub `CvSummary` / `CvPreview` | **deliberately not built.** See below |

**Why no stubs.** A stub that shows a fake CV, preview and upload on screen
would need a mock of three routes. It is also the exact kind of fabricated
output this file deleted `stubs.js` over. And with no Node on this machine,
there's no dev server to use them in. Instead the screens are built against the
real contract, and the honest `unavailable` state is what renders until the
routes exist.

## How it behaves against today's backend

`GET /api/profile/cv` → 404 → the strip reads "CV · shared sample CV (not yours) —
uploading your own isn't available on this server yet", with no buttons. Start
works as before, and the run screen says "tailoring: sample CV (not yours)".
Nothing that works today is blocked.

## Contract this code now relies on

The backend asks are in `backend/bugs.md` → 2026-10-09 (later). Listed here
because breaking any of these changes behaviour:
- `GET /api/profile/cv` answers `{cv: CvSummary | null}`, **never 404 for "no
  CV"**. A 404 is read as "routes not deployed" and unblocks Start.
- `POST /api/profile/cv` → `{cv, preview}`; `POST /api/profile/cv/{id}/confirm`
  → `{cv}`; `DELETE /api/profile/cv/{id}` → 204.
- 422 `detail` contains the code string (`no_text` etc.).
- `POST /runs` answers 409 for no CV, before any run is spent.
- Which CV a run used arrives as `cv: {id, filename}` on the `POST /runs` reply,
  a `run_started` event, or the run summary. It never carries CV text.
  `sample: true` in the same places means the server fell back to its shared
  sample, and the run is labelled "sample CV (not yours)".

## Verification status: **not run**

No build and no browser (no Node here; the standing rule is to ask first).
Checked: brackets balance in all ten touched files, every imported name exists,
and diffs against pre-edit copies.

**The check to ask for, today:** build, sign in as a user, and confirm:
- the Pipeline and Account strips read "shared sample CV — … isn't available on
  this server yet";
- Start is enabled;
- the run screen says "tailoring: sample CV (not yours)".

**Once the routes land:**
- a user with no CV sees Start disabled, with the reason;
- dropping a `.txt` renamed to `.pdf` shows "This file isn't a PDF." and sends
  nothing (check the network tab);
- a real PDF shows a progress %, then "reading your CV", then "What we read";
- Cancel sends a DELETE;
- "Use this CV" updates both strips at once;
- in Account, Delete → confirm → the Pipeline strip says "none yet" and Start is
  disabled again.

---

# Round 13 — gate 4, the final review: what was built here, and what the frontend still needs (2026-10-09)

Written by **Agents + Orchestration (Claude)**, which wired gate 4 across the graph,
backend, frontend and knowledge base the same day (work log: `context/context.md` →
2026-10-09 "Gate 4 wired end to end"; open items: `context/bugs_audit_fixed.md` #55;
backend half: `backend/bugs.md` → "2026-10-09 (gate 4)"). It edited files in
**this folder**, so this round starts with exactly what changed. Round 12 ("Your CV")
was built in parallel and deliberately did not touch `GateScreen` / `FinalOutput`.

## What changed in `frontend/src` (not built, not run)

| File | Change |
|---|---|
| `components/PipelineView.jsx` | `applyEvent`: `gate_wait` stores `name` (`ev.gate`) and `changes`; a new `document_edited` case replaces `artifacts.document`; `run_done` stores `final`. `IDLE.final = null`. `answerGate(decision, feedback, gapAnswers, {gate, editedContent})` sends `gate` and, with `edit` only, `edited_content`. Passes `verifierStub` to `GateScreen`, and `verifierStub`, `final`, `runId` to `FinalOutput`. |
| `components/GateScreen.jsx` | **The gate-4 variant.** `isFinal` comes from `gate.name === "gate4_document"`, falling back to `artifactNode === "document"` for old logs. Adds "What changed from your CV" (one card per change: where, struck-through before, after, why). **"Edit the CV"** swaps the read-only CV for a 50,000-char textarea pre-filled with the draft, with **Save my edits and finish** (disabled while blank or unchanged) and **Cancel** (restores the draft). The fact check shows `FACT_CHECK_PENDING` instead of the stub's "all claims check out" when `verifierStub`. Gates 1–3 are unchanged. |
| `components/FinalOutput.jsx` | `extractFinalArtifacts` also folds in `document_edited` (your edit wins over the Writer's draft), `run_done.final` and the verifier's stub flag. Shows the review status (approved / approved with your edits / not approved). **Download** fetches the server's saved copy via `GET /api/runs/{id}/document?fmt=md` when `final.export.md` exists, and otherwise falls back to the in-page blob, saying so on error. The fact-check note is the same as the gate's. |
| `components/RunsView.jsx` | Passes `runId={openLog.id}` so past runs download the server copy. |
| `components/RunLog.jsx` | Adds a line for `document_edited`; `gate_done` with `edited` reads "you edited the CV"; `run_done` appends "· CV saved" or "· last draft not approved, not saved". |
| `api.js` | `download(path, filename)`: an authenticated fetch, then a blob save (a plain `<a href>` cannot carry the bearer token). Same `ApiError` / 401 handling as `request()`. |
| `copy.js` | `FINAL_CHANGES_HEADING`, `FINAL_NO_CHANGES`, `FINAL_EDIT_HELP`, `FACT_CHECK_PENDING`, `FINAL_APPROVED`, `FINAL_APPROVED_EDITED`, `FINAL_NOT_APPROVED`. |

## How the final review behaves now

```
gate_wait {gate: "gate4_document", changes[], ...}   → GateScreen (isFinal)
   ├─ Approve                         → POST {decision: "approve", gate}           → … run_done.final.review.approved = true, export set
   ├─ Edit the CV → Save my edits     → POST {decision: "edit", gate, edited_content}
   │                                    → document_edited (artifact replaced) → … run_done.final {approved, edited: true, export}
   └─ Reject                          → POST {decision: "reject", gate}
         ├─ budget left  → Writer → Reviewer → Fact Check run again → a NEW gate_wait (new ts → fresh screen, new changes)
         └─ budget spent → run_done.final {approved: false, export: null} → FinalOutput: "not approved … not saved"
```

The rule behind the last split is `decide()` in `agents/supervisor.py`: a reject is
honoured only while `revision < max_revisions`. The Reviewer's REVISE and the Fact
Check's FAIL spend the same budget.

## Needed from the frontend

### 1. 🔴 Build it and look at it: none of the above has been parsed

Same caveat as Rounds 8–12: no build and no browser. Every edited region was re-read
by eye. Hooks are called unconditionally (the new `useState`s in `GateScreen` sit above
any return, and `FinalOutput`'s `downloadError` sits above its early `return null`).

**The check to ask for:** `docker compose -f frontend/docker-compose.yml build frontend`,
then three demo runs:
- **Approve at gate 4.**
  - The screen lists changed lines, or "No lines were changed".
  - The fact check says "Not checked yet…".
  - The final output reads "approved at the final review — saved".
  - Download saves a `.md` whose name starts with today's date.
- **Edit the CV.** Change one line and save.
  - The log shows "your edited CV replaced the draft" and "you edited the CV".
  - The final output shows **your** text and "approved with your edits — saved".
- **Reject until the limit.**
  - The screen reopens with a fresh form each round.
  - The end reads "not approved … not saved".
  - Download still works, from the page's copy.

### 2. ✅ The fit review still shows an empty "Fact check" block (Round 9's open item, now a one-liner) — **fixed 2026-10-09 (Round 14)**

`showsVerifierToo` is still `artifactNode !== gate.node`, and gate 3 is `matching` vs
`cv_link`. The gate name is on the wire now, so:

```jsx
// move the isFinal line above this one, then:
const showsVerifierToo = isFinal;
```

That's the contract Round 9 asked for, and it can't break again when a gate moves.

### 3. ✅ A refused answer should retire the form, not sit there with an error — **fixed 2026-10-10 (Round 17)**

The backend now answers **409** when the form's `gate` is no longer the open one. Soon
it will also answer 409 for a second answer to the same gate (`backend/bugs.md` →
gate 4, item 1). `GateScreen` currently prints `err.message` and leaves every button
live.

> **✅ Landed 2026-10-10.** The "soon" above is no longer soon: every run gets
> its own lock, and a second POST to an already-answered gate now gets
> `409 "This review was already answered"` (`backend/bugs.md` → gate 4, item
> 1). No shape change — it's the same 409 this item already designed for, so
> the handling below covers it as written; nothing new to build here.
- **On 409:** replace the buttons with "This checkpoint has moved on — the run
  continued", and send nothing more. The SSE stream brings the next `gate_wait` (new
  `ts`, so a fresh screen) or `run_done`. Don't refetch anything.
- **On 422 while editing:** keep the editor open with the text intact, and show
  "Your edit couldn't be saved: <detail>". Losing a typed CV to a validation error is
  the worst outcome on this screen.
- **On 0 (unreachable):** keep everything, and say "Couldn't reach the server — your
  decision wasn't sent".

### 4. 🟠 Warn before a reject that ends the run without saving

Gate 4 can open with the revision budget already spent, because the Reviewer and Fact
Check loop-backs use the same budget. A reject then saves nothing and ends the run, and
today nothing on screen says so.
- **Needs** `revision` and `max_revisions` on `gate_wait` (`backend/bugs.md` → gate 4,
  item 3; one line in the gate payload, Agents lane). Store them in `applyEvent` next
  to `name`.
- **Header chip:** "round {revision + 1} of {max_revisions + 1}". Show it only from
  the second round on, so a first run isn't cluttered.
- **When `revision >= max_revisions`:**
  - Reject becomes **"Reject and finish without saving"**, with an inline two-step
    confirm: the button turns into "Yes, finish without saving" plus "Keep reviewing".
    No `window.confirm` or modal: design.md's rule for destructive actions.
  - Put one line next to it: "This is the last round — editing the CV is the way to
    change it now."

### 5. ✅ Say what a reject actually does today — **fixed 2026-10-10 (Round 18)**

Document doesn't read the human's reason yet (`bugs_audit_fixed.md` #55.1). It keeps
its plan on a redo, so a reject returns a **very similar draft**. The screen implies
otherwise.
- **Under Reject, in `copy.js`:** "Rejecting asks the writer for another draft. It
  doesn't use your reason yet, so expect something similar — editing the CV is the
  reliable way to change it."
- **Remove** that line when the Agents lane lands the revision input. At that point the
  feedback placeholder at gate 4 becomes "What should the writer change? (used for the
  next draft)", and the backend may start requiring a reason on a gate-4 reject
  (`backend/bugs.md` → gate 4, item 9c). Handle that `422 reason_required` by focusing
  the feedback box.

### 6. 🟠 Don't lose an edit in progress — **leave-page prompt and Cancel confirm done 2026-10-09 (Round 15); the localStorage draft deliberately deferred**

A CV-length edit is the most expensive thing anyone types into this app.
- **Keep a draft in `localStorage`** under `gate4-edit:${runId}:${gate.ts}`, written on
  change (debounced, about 500 ms).
  - When an editor for the same key mounts, restore the draft with a note: "restored
    your unsaved edit".
  - Clear it after a successful answer, and on Cancel.
  - Keying on `ts` means a reopened gate (new round, new draft) never restores an edit
    of the old draft.
- **`beforeunload` while `editing && editChanged`.** It's the browser's own leave-page
  prompt, the one acceptable dialog here.
- **Cancel with changes** gets an inline confirm ("Discard your edits?"), not an
  immediate reset.
- **No server needed.** The text is the user's own CV in their own browser, and the
  key is cleared on answer.

### 7. ✅ Read `final` on `run_error` too — **fixed 2026-10-10 (Round 21); the backend sends it since the same day**

`backend/bugs.md` → gate 4, item 2: when a step after gate 4 fails, the worker will
still save the approved CV and attach `final` to `run_error`.
- In `applyEvent`, `case "run_error": next.final = ev.final || null; …`. Do the same
  in `extractFinalArtifacts`.
- `FinalOutput` then renders on an errored run, with the saved status plus "a later
  step failed: <error>".
- Harmless before the backend lands it: the field is just absent.

> **✅ Landed 2026-10-10.** `run_worker` now calls the same closing step on a
> post-build failure that it calls on a clean finish, so `run_error` carries
> `final` (the approved review + export paths) whenever the graph had
> already been built — i.e. whenever the failure happened after gate 4, the
> case this item exists for. A failure *before* the graph builds still omits
> `final` entirely (same as "the field is just absent" above), so the
> `ev.final || null` fallback this item already specifies is still exactly
> right; nothing here needs to change. **This is now the one genuinely
> needed item from this round** — without it, a run that fails after an
> approved/edited CV still shows as a bare failure in the UI even though the
> backend saved the file.

### 8. 🟡 Undo a single change (design; needs the backend and Agents lanes first)

The most-wanted control on this screen: keep the good edits, drop the bad one.
- **UI:** each change card gets a **Keep / Undo** toggle (default Keep).
  - The footer reads "Approve" while nothing is undone, and "Approve with 2 changes
    undone" otherwise.
  - That sends `decision: "approve"` with `reverted_changes: [node_id, …]`.
  - Undone cards dim their "after" line and un-strike their "before" line.
- **Contract:** `backend/bugs.md` → gate 4, item 9a. The gate rebuilds the CV from the
  original plus the kept edits (deterministic, no model). The backend 422s ids that
  weren't in this gate's `changes`, or `reverted_changes` sent together with
  `edited_content`.
- **Rejected alternative: composing the edited CV in the browser** (string-replace each
  undone "after" with its "before" in the Markdown, then send it as `edited_content`).
  The Markdown has no node ids. A line can repeat. Skills are joined with ` | ` into
  one Markdown line per group. So the replace isn't safe. Don't build it.
- **Don't build the toggle** until 9a lands: an Undo that does nothing is worse than none.

### 9. 🟡 Make the diff readable

> **Done 2026-10-12 (Round 37)**, as specified below. One change: the evidence
> map is built from every `node_done` in the run, not only the latest artifact
> per step.

- **Word-level highlight** inside each card: a small LCS over whitespace-split words
  (lines are under 40 words, so O(n·m) is fine). No library.
- **Labels, not just colour:** "was" / "now" before the two lines. The red/green pair
  alone fails for red-green colour blindness.
- **Group by section.** `where` is "Section › Entry"; group cards under the section and
  show the entry as a sub-heading.
- **Evidence on expand.** `evidence_ids` are profile record ids. Their text is already in
  the run's artifacts: `artifacts.document.evidence` holds the records Document fetched,
  and `artifacts.profile.evidence` / `artifacts.profile_enrich.evidence` hold the rest,
  all `{source_id, content}`. Build one `source_id → content` map in `PipelineView` and
  pass it down. An id that isn't found shows as the id, dimmed. This is the "why should
  I trust this line" answer, and the Fact Check can't give it yet.

### 10. 🟡 Editor comfort

> **Done 2026-10-13 (Round 38)**, as specified below, plus a one-line note that
> the preview is a reading view, not the PDF's layout.

- **"Reset to the draft"** inside the editor, with an inline confirm when changed.
- **A character count** that turns amber past 45,000 (the backend cap is 50,000; the
  textarea's `maxLength` already stops typing at the cap).
- **A Preview toggle** that renders the edited Markdown read-only. Only what
  `render_markdown` emits needs handling: `#`, `##`, `###`, `- ` and `**bold**`. A
  ten-line renderer, no library, and no HTML injection, because it builds elements,
  not `innerHTML`.

### 11. 🟡 Final output: both formats, and say where it went

> **Done 2026-10-12 (Round 36)**, except the "Start a new run" offer (see top
> item 14).

- **Two buttons:** "Download .md" and "Download .txt". The route takes `fmt=txt`
  (Markdown stripped, bullets as "•").
- Under the status, "saved as `<filename>`" (the basename of `final.export.md`).
- **When not approved:** label the card "last draft (not approved)" rather than "final
  output", and offer "Start a new run".

### 12. ✅ The feedback label should say what really happens (#55.6) — **fixed 2026-10-10 (Round 25)**

"Feedback (recorded in the run's audit trail and agent memory)" is true only at gate 4,
and only on live runs. Per gate:

| Where | Label |
|---|---|
| Gates 1–3 | "Feedback (saved with this run's history)" |
| Gate 4, live | "Feedback (saved with this run, and kept so later runs can learn from it)" |
| Gate 4, demo | "Feedback (saved with this run; demo runs aren't kept for learning)" |

`GateScreen` already has `demo` and `isFinal`, so no new props are needed.

### 13. ✅ "Request edit" at gates 1–3 does nothing a user would call an edit (#55.5) — **fixed 2026-10-10 (Round 22)**

`decide()` treats `edit` like `approve` there: the run moves on, and only the note is
recorded.
- **Rename it "Approve with a note".** Keep sending `decision: "edit"` so the audit
  trail keeps the distinction.
- Disable it until the feedback box has text, since without a note it's just Approve.
- Revisit when the gate redesign (design §C.4) gives `edit` a meaning per gate.

### 14. ⚪ Saved CVs on Runs and Account

Once `GET /api/runs` summaries carry `review` and `saved` (`backend/bugs.md` → gate 4,
item 5b):
- a "saved" chip per row, plus a row-level download (the same `api.download` call);
- on Account, "Your saved CVs" with a delete per item once `DELETE
  /api/runs/{id}/document` exists (5c), confirmed inline;
- "Resume" for `interrupted: true` rows once item 7's route lands. The replayed
  `gate_wait` reopens the same review screen.

### 15. ✅ A demo-mode note at gate 4 — **covered 2026-10-10 (Rounds 25–26: the feedback label and the editor text both carry it)**

Like `GAP_DEMO_NOTE` at gate 2: "Demo run: your edit becomes the final CV and is saved as
a file, but it isn't kept for learning." It's true today (`close_run` skips the learning
store offline).

## Contract the screens use

| Event or call | Fields | Notes |
|---|---|---|
| `gate_wait` | `gate`, `node`, `title`, `artifact_node`, `gap_questions` (always present), `changes` (gate 4) | `changes[] = {node_id, where, before, after, reason, evidence_ids}`. Coming: `revision`, `max_revisions` (item 4) |
| `gate_done` | `gate`, `node`, `decision`, `feedback`, `gap_answers`, `edited` | never the edited text. **`gate` built 2026-10-15** — no longer "coming"; matches `gate_wait.gate`, so a replayed log needs no guessing which checkpoint a given `gate_done` answered |
| `document_edited` | `artifact: {document: {kind, content, unsupported_flags, …}}` | only after a gate-4 edit with changed text |
| `cv_link`'s `node_done` | `artifact: {cv_tree, line_links}`, plus a top-level `match_counts: {matched, partial, unmatched}` | **`match_counts` built 2026-10-15** — a server-side tally over `line_links`' three current statuses, so item 20 (the empty-profile warning) doesn't need you to walk the list yourself |
| `run_done` | `final` (or `final: null` plus `final_error`) | `final = {review: {decision, approved, edited, revision, rounds} \| null, export: {md, txt} \| null, learning}`. Old logs have no `final` |
| `run_error` | `error`; coming: `final` (item 7) | |
| `GET /api/runs` | per-row: `id`, `started`, `mode`, `job_description` (120 chars), `events`, `completed`, `cv`, `sample_cv`, plus **`review`, `saved`, `interrupted`, `outcome`** | `review`/`saved` built 2026-10-13 (items 22/26), `interrupted` 2026-10-13 (item 21), `outcome: "done"\|"stopped"\|"error"\|null` built 2026-10-15 (item 18). All additive; `completed` is unchanged |
| `POST /api/runs/{id}/gate` | `{decision, feedback, gap_answers, gate?, edited_content?}` | 409 stale or duplicate; 422 `edited_content` outside a gate-4 edit. Coming: `reverted_changes`, `discard`, `reason_required` (backend item 9) |
| `GET /api/runs/{id}/document?fmt=md\|txt` | a file (`attachment; filename=…`) | 404 when not saved or deleted; 403 another user (never treat as 401). **Now also serves a CV whose `final` landed on `run_error`** (item 26, A1, 2026-10-15) |
| `DELETE /api/runs/{id}/document` | none in, `204` out | **New, built 2026-10-13** (item 22). Owner-checked, 403 never 401; removes both `.md`/`.txt`; a later `GET` 404s the same way "never saved" does |
| `POST /api/runs/{id}/resume` | none in, `{run_id}` out | **New, built 2026-10-13** (item 21). Owner-checked; 409 if a worker already owns the run or it isn't parked at a gate; never spends another allowance. Reconnect the SSE stream after calling it — the replayed log already has the open `gate_wait` |

## Blockers that are not the frontend's

- **Document ignores the human's reason on a reject** (`bugs_audit_fixed.md` #55.1,
  Agents lane). Items 5 and 8 depend on it.
- **Round info on the gate payload** (Agents lane), then items 4 and 13's revisit.
- **The Verifier is still a placeholder.** When it's real, `stub` on its `node_done` turns
  false, and both screens render the real report with no frontend change.
- **Backend items 1, 2, 5 and 9** in `backend/bugs.md` → "2026-10-09 (gate 4)".

## Verification status: **not run**

The built rows were checked from the backend side only: the scratch run of the graph,
closing step and export, and the in-process route check (`backend/bugs.md` → gate 4,
"Verification status"). Nothing in this folder was built or opened in a browser.
Standing rule: no frontend build or serve without asking first.

---

# Round 14 — the fit review loses its empty "Fact check" block (2026-10-09)

Round 13 item 2 (and Round 9's open item). Frontend only, `GateScreen.jsx` only.

**Why this one next.** Round 13's two 🔴s were this and item 1, "build it and look
at it". Item 1 isn't code: it needs a Docker build, which is asked for, never
assumed. This was the only 🔴 that is code, frontend-only, and visible on every
run: the fit review showed "Fact check · output of CV Reader — no output yet"
under the fit report.

## What changed

- `showsVerifierToo` is now `isFinal`. That is keyed on the gate's name
  (`gate4_document`), with Round 13's fallback (`artifactNode === "document"`)
  for logs that carry no name. `isFinal` moved above it. No hooks moved, so the
  call order is unchanged.
- The block now renders the Fact Check explicitly: the label is
  `AGENT_TITLES.verifier`, and the body is `renderArtifact("verifier", …)`.
  Before, it used `gate.node`, which is right at gate 4 today only because that
  gate sits after `verifier`. Now moving a gate can't mislabel it again.

Old logs, checked by reasoning:
- a gate-4 `gate_wait` without `gate` still has `artifact_node: "document"`, so
  the block still shows;
- a pre-`cv_link` gate 3 (`after: matching`) never had `artifact_node:
  "document"`, so it still doesn't.

## Verification status: **not run**

Brackets balance, and the diff against the pre-edit copy touches only those
lines. **Round 13 item 1 is now the most important open item in this folder.**
Rounds 8, 9, 10, 12, 13 and 14 have all been written without a single build;
Round 3 is the reminder of what that can hide. Check with
`docker compose -f frontend/docker-compose.yml build frontend`. Then, in a
demo run:
- the fit review shows **no** Fact check block;
- the final review still shows one ("Not checked yet…" while the verifier is a
  placeholder).

---

# Round 15 — an edit at the final review can't vanish silently (2026-10-09)

Round 13 item 6. Frontend only: `GateScreen.jsx` plus one string in `copy.js`.

**Why this one next.** The build (Round 13 item 1) is still the most critical item,
but it needs an explicit yes, and it wasn't given. Of the code items left, this
one has the worst outcome. An edit at the final review is a whole CV typed by
hand, and before this round it could disappear without any warning in three
ways:
- a reload;
- closing the tab;
- one click on Cancel.

The other 🟠s in Round 13 are smaller:
- item 3: a 409 leaves a stale form live for a moment;
- item 5: misleading copy;
- items 4 and 7: wait on backend fields.

## What changed

- **The browser's leave-page prompt while an unsaved edit exists.** The
  condition is `isFinal && editing && editChanged`, so it's registered only
  then, and the effect's cleanup removes it the moment that stops being true:
  - after a save (the gate closes and the screen unmounts);
  - after a discard;
  - when the text is changed back to the draft.

  Nowhere else in the app triggers it. It's the one dialog design.md allows.
- **Cancel with changes asks first, inline.** The buttons are replaced by
  "Discard your edits? The CV goes back to the draft." with **Discard** and
  **Keep editing**. Cancel with no changes closes the editor at once, as before.
- **Already safe, so unchanged:** a failed save (422, unreachable) leaves the
  editor open with the text intact; only the error line appears. Switching to
  another view doesn't unmount the screen, so the edit survives that too.

## Deliberately not done: the localStorage draft

Round 13 asked for a draft under `gate4-edit:${runId}:${gate.ts}`, restored on
remount. **Today nothing can remount that screen.** After a reload the run is
gone from the page: there is no Resume (Round 13 item 14, `backend/context.md`
D7), and a paused run isn't even listed in Runs until it finishes (Round 7
item 3). A stored draft could never be restored. Storing a full CV in the
browser with no way to restore it is cost without benefit. **Build it together
with Resume.** Then the key and the restore note can go in as Round 13
specified.

## Still able to lose an edit (not fixed here)

- **Logging out mid-edit**, or a central 401. Either unmounts the whole app, and
  `beforeunload` doesn't fire for in-app navigation. This is Feature 15a
  ("confirm logout mid-run"), still deferred.
- **"new run" after the stream drops.** If the SSE connection is lost while
  editing, the "new run" link appears and resets the run with no prompt. Saving
  still works in that state, because answers go over POST, not the stream.

## Verification status: **not run**

Brackets balance, every import resolves, and the diff against the pre-edit copy
touches only the lines above. Once built, in a demo run at the final review:
- **Edit the CV**, change a line, then press reload. The browser asks before
  leaving.
- **Cancel** shows the inline confirm. "Keep editing" keeps your text, and
  "Discard" restores the draft.
- **Cancel with no changes** closes the editor at once.
- **Save my edits and finish**, then reload. No prompt.

<!-- ============================================================ -->

---

# Round 16 — one launcher for the whole system, `scripts/dev.py` (written 2026-09-16, logged 2026-10-10)

> **Nothing in `frontend/src` changed.** This round is a runner script plus the
> doc updates around it. It is logged here because it is how this folder now
> gets started and watched, but **the file itself is not this folder's
> jurisdiction** — `scripts/dev.py` sits in the Pipeline + Infra + Config lane
> (`context/context_Pipeline Infra+Config+Testing.md`). Changes to it belong to
> that role; this entry is the Frontend-side record of what it does and where it
> doesn't work.

## What it is

Before this, starting the system meant two commands in two terminals from two
different directories (`DELIVERABLES.md` → "How to start it"), and watching the
API meant reading whichever terminal uvicorn happened to be in. `scripts/dev.py`
collapses that into one process supervisor:

| command | what it does |
|---|---|
| `python scripts/dev.py up` | uvicorn :8000 + the Vite dev server :5173, output merged and prefixed |
| `up --docker` | uvicorn + the nginx image on :3000 instead of Vite |
| `up --no-frontend` | backend only |
| `up --offline` | backend starts with `USE_FAKE_LLM=1`, so runs default to demo mode |
| `up --reload` | uvicorn restarts on code edits |
| `monitor` | follows the API calls of a running `up`, from a second terminal |
| `smoke` | `scripts/smoke_backend.py`, starting a server first only if none is healthy |
| `test` | `pytest tests/` |
| `check` | preflight + `main.py` config summary, starts nothing |

Three things in it are worth knowing:

- **It parses uvicorn's access log.** `ACCESS_RE` pulls method/path/status out of
  each access line and reprints it coloured by status class, so every `/api/*`
  call shows up as it happens. On exit it prints a per-route count. That is the
  whole of the "monitoring" story — there is no separate monitor service, and
  the backend has **no request-logging middleware** of its own (`backend/app.py`
  only has a startup `ADMIN_TOKEN` warning).
- **Output is tee'd to `logs/dev/<name>-<timestamp>.log`.** That is what makes
  `monitor` possible from another terminal while `up` keeps running. `logs/` is
  already git-ignored, so no `.gitignore` change was needed.
- **It kills the process group, not the leader** (`os.killpg`), because
  `uvicorn --reload` and `npm` both spawn children that otherwise survive and
  keep holding the port.

## 🔴 1. The default `up` cannot work on this machine

`up` with no flags starts the frontend with `npm run dev`. There is **no Node
and no `node_modules` on the dev machine** (`context.md` → "Local environment
note"), so on this machine the only working frontend path is **`up --docker`**.

Worse, the preflight gives the wrong advice for it. `preflight()` detects the
missing `node_modules` and prints:

```
frontend/node_modules is missing — run:  cd frontend && npm install
      (or use --docker, which builds node inside the image)
```

`npm install` is not runnable here at all — there is no npm. The parenthetical
is the real answer on this machine, and it reads as the afterthought. Either
`--docker` should be the default when `node_modules` is absent, or the message
should lead with it. **Not fixed** — the file is out of this folder's lane.

## 🟠 2. It has never been run

Written 2026-09-16 and handed over unrun, like Rounds 8–15. Nothing in it has
been executed: not `check`, not `up`, not `monitor`. The process supervision
(signal handling, group kill, the reader threads), the access-log regex against
real uvicorn output, and the docker `up`/`down` pair are all unverified.

It also **changed on disk after it was written** (~17.6 KB on 2026-10-10 against
the handed-over version). Re-read it before changing anything; this entry
describes the version as written.

## 🟡 3. `monitor` only sees a backend that `up` started

`monitor` tails the newest `logs/dev/backend-*.log`. A backend started by hand —
`.venv/bin/python -m uvicorn scripts.frontend_api:app --port 8000`, which is
still what `DELIVERABLES.md` documents and what every past session has used —
writes nothing there, so `monitor` reports "no backend log" and exits 1 even
though a backend is plainly running on :8000. It is not a general-purpose API
watcher; it is the second half of `up`.

## 🟡 4. `up --docker` builds the frontend image

The standing rule ("never build, serve or bundle the frontend unprompted, not
even a throwaway `--rm` container") binds **the assistant**, not the user
running their own launcher. But it does mean the assistant must not run
`dev.py up`, `up --docker` or `smoke` to check any of the above — the user runs
it and reports back, same as every other round here.

## Verification status: **not run**

What to check, in order, once someone runs it:

1. `python scripts/dev.py check` — starts nothing. Confirms the venv resolves,
   reports whether `ADMIN_TOKEN` is set, and whether :8000/:5173/:3000 are free.
   Expect it to flag `node_modules` as missing (see #1) — that is correct here.
2. `python scripts/dev.py up --docker --offline` — expect the backend banner,
   the docker build, then `/api/health` answering on :8000 and the dashboard on
   :3000. Every click in the UI should print an access line in the terminal.
3. In a second terminal, `python scripts/dev.py monitor` — expect only `/api/*`
   lines, newest first as they arrive, and a per-route count on Ctrl-C.
4. Ctrl-C the `up` terminal — expect the container to come down
   (`docker compose … down`) and no uvicorn left holding :8000
   (`lsof -ti:8000` prints nothing).
5. `python scripts/dev.py smoke` — expect it to reuse the running backend if one
   is up rather than starting a second, and to leave it running afterwards.

---

# Session summary — Frontend lane, 2026-10-09/10 (Rounds 8, 9, 10, 12, 14, 15)

A one-page record of one working session, so the next one doesn't have to
re-read six rounds to know where things stand. **Each round above has the
detail. This entry adds only what no single round says:**
- the session as a whole;
- the decisions it made;
- what it got wrong and corrected;
- the order of what's next.

**Authority:**
- **Code:** write access to `frontend/` only, granted by the user for each
  build.
- **Outside `frontend/`, documentation only:** `backend/bugs.md`, on request.
- **Not run, under the standing rule:** no build, serve or bundle. **Nothing
  below has been compiled.**

## What was built

| Round | What | Files | Backend dependency |
|---|---|---|---|
| 8 | Gate-2 answer form: one box per follow-up question, nothing sent on reject, fresh form per reopen, demo-mode warning | `GateScreen`, `PipelineView`, `RunLog`, `copy.js` | none: the backend half existed since 2026-08-31 |
| 9 | `cv_link` drawn as "CV Reader", a counts card, a per-line drawer, and the earlier read kept on a re-run | `AgentGraph`, `StatePanel`, `PipelineView` | none: the backend half landed 2026-10-08 |
| 10 | One click, one run: an in-flight guard on Start, and the previous stream closed before a new one opens | `PipelineView` | only an idempotency key covers two tabs |
| 12 | CV upload, frontend half: shared CV state, the strip, "What we read", Account row, run header, error table, nginx 6 MB | `CvContext` (new), `CvStrip` (new), `CvPreview` (new), `api.js`, `App`, `PipelineView`, `Account`, `RunsView`, `RunLog`, `copy.js`, `nginx.conf` | **all four `/api/profile/cv` routes.** Until they exist it shows the shared sample, honestly, and blocks nothing |
| 14 | The fit review loses its empty "Fact check" block; the block keys on the gate name | `GateScreen` | none |
| 15 | An edit at the final review is guarded: a leave-page prompt, and an inline Cancel confirm | `GateScreen`, `copy.js` | none |

Not this session's, but built in parallel in the same files:
- **Round 13**, the final review, by the Agents session;
- **Round 16**, `scripts/dev.py`, Infra lane.

Round 11 (CV scoping) was also written by another session, and Round 12 builds
from it.

## Documentation written outside this folder

- `backend/bugs.md` → **"2026-10-09 — what frontend Rounds 8–10 need from the
  backend"**, eight items:
  - caps, gate-scoping and a reject rule for `gap_answers`;
  - the demo-mode profile write (for the `learning/` lane);
  - a `gate` name on gate events (it has since shipped);
  - an idempotency key, plus a per-owner lock in `registry.start`, which can
    leave two live runs for one user today;
  - a slimmer, privacy-safe `cv_link` event;
  - "unchanged" instead of `{stage}` on a re-run;
  - and two fields that were already asked for.
- `backend/bugs.md` → **an addendum to "2026-10-09 (later)"**, the CV spec. It
  pins down five contract points the frontend relies on. The one that matters
  most: "no CV" must be `200 {cv: null}`, never a 404.
- Status lines on `backend/bugs.md` 2026-10-08 items 1 and 3.
- `frontend/context.md`, rewritten to match the code and kept current through
  every round. `DELIVERABLES.md` got two "written, not yet built" lines.

## Decisions made, and where they're recorded

- **CV upload is in Stage 0 (D-CV1).** With no CV, a user can't start; the admin
  may run on the sample, labelled (D-CV2, the design's recommendation).
  `backend/bugs.md` §3 says the admin needs a CV too. The frontend handles both,
  but **the user should pick one** (addendum point 4).
- **A 404 on `GET /api/profile/cv` means "not deployed"**, so the frontend keeps
  working against today's backend.
- **No stub or fixture data for the CV screens**, though Round 11 asked for it.
  It would put a fabricated CV on screen, which is the `stubs.js` lesson.
- **The localStorage draft for a gate-4 edit is deferred until Resume exists.**
  Nothing can reopen that screen today, so the draft could never be restored.
- **`frontend/nginx.conf`'s body limit was set here.** Round 11 had filed it
  under the backend, but the file is this folder's.

## What this session got wrong, and corrected

- **Round 9 recorded two backend fixes as still open** ("no node_start for CV
  Reader", "gate 3 still after matching"). Both had landed the day before. The
  claims were copied from Round 6's notes instead of checked in
  `backend/runs/worker.py`. It was caught while writing the backend asks, and
  corrected in Round 9's entry, `context.md` and the summary to the user.
  Checking it also surfaced the gate-3 "Fact check" regression (fixed in Round
  14). **Rule now in `context.md` §4: check the backend in code before writing
  down what it owes.**
- **A first ranking listed CV upload as buildable.** Its backend routes don't
  exist, so the gate-2 form was built first, and CV upload was later built to
  degrade honestly.

## Working conditions worth knowing

- **`frontend/` is untracked in git.** Every round's pre-edit copies went to the
  session scratchpad (`…/scratchpad/backup/` for Round 8, and
  `backup/round{9,10,12,14,15}`), which is not kept. Once this session ends there is no undo but the code itself. Commit the
  folder, or copy a file before editing it.
- **Three sessions edited overlapping files the same day** (this one, Agents,
  Infra). Twice an edit was refused, or a file changed between read and write;
  re-reading fixed both. One duplicate paragraph (the `dev.py` start command in
  `context.md`) was caught and removed.

## Where things stand, in order

> **Superseded 2026-10-10** by "Open work, by criticality" at the top of this
> file. Items 2–5 below were closed by Rounds 17–21; item 7 is top-list item 12.

1. 🔴 **Build it.**
   `docker compose -f frontend/docker-compose.yml build frontend`. It compiles
   only. Asked for at the end of this session; still awaiting an explicit yes.
   Then each round's "how to verify" list, newest first (15 → 8).
2. 🟠 **Round 13 item 3:** on a 409, retire the gate form instead of leaving it
   live. Smallest remaining 🟠 that is pure frontend.
3. 🟠 **Round 13 item 5:** honest reject copy at the final review.
4. 🟠 **A reopened gate's "revised version" signal.** A client-side count of
   repeat `gate_wait`s for the same gate works today, with no backend change.
5. 🟠 **Round 13 item 7:** read `final` on `run_error`. Harmless before the
   backend sends it.
6. 🟡 The rest of Round 13 (8–15), the Round 5 leftovers, and the localStorage
   draft once Resume exists.
7. 🟡 **New, 2026-10-10:** `GateScreen`'s feedback `<textarea>` (used at every
   gate) has no `maxLength` at all — unlike the gap-answer inputs, which
   already have `maxLength={2000}` as a courtesy. The backend now caps
   `feedback` at 2,000 characters server-side (`backend/bugs.md` → gate 4,
   item 4). Add the matching `maxLength={2000}`, same reasoning as the
   gap-answer boxes: nothing breaks without it (a user just gets a 422 after
   typing past 2,000 characters, same fallback as item 3 above, before its
   own fix), but it's a one-line courtesy that avoids it.

**Blocked on other lanes:**
- ~~the CV routes~~ — ✅ built 2026-10-10 (`backend/bugs.md` → "later", CV upload). Round 11/12 already cover the frontend half.
- `revision` / `max_revisions` on `gate_wait` — still open; needs `utils/human_gate.py` (Agents lane), not backend.
- ~~an idempotency key and a per-owner lock~~ — ✅ built 2026-10-10 (`backend/bugs.md` → "Round 8-10" #4). **Frontend action still needed:** send `client_request_id` from `start()` (Round 10, above).
- ~~a privacy-safe `cv_link` event~~ — ✅ partly built 2026-10-10 (the header + `raw_text` scrub, Round 7 section above). The size/shape question (per-line text, moving it behind its own route) is still open, by design — see that section's new note.
- the demo-mode profile write (`learning/`) — still open; Data Storage/Agents lane, not backend.
- the unmatched count — still open; not touched this session.

---

# Backend session, 2026-10-10 — what it fixed, and what it leaves this lane

> Written from `backend/`, reporting in. Five fixes this session, all inside
> `backend/`, each logged in full at its own dated entry in `backend/bugs.md`.
> This section is only the cross-reference: what each one means here, not a
> repeat of the backend-side detail. Nothing in this folder was built, served,
> or changed by this note — per standing instruction, that needs asking first.

| Backend fix (`backend/bugs.md`) | Frontend action needed | Where it's annotated above |
|---|---|---|
| Gate double-answer race (409 on a second answer) | None. Already designed for | Round 13, item 3 |
| Two-starts-per-owner race + idempotency key | **Send `client_request_id`** from `start()` | Round 10, "Still open, backend side" |
| Approved CV lost on a post-gate-4 failure | **Read `final` on `run_error`** — this is the one that actually changes what the screen should show | Round 13, item 7 |
| `cv_link` privacy scrub (header + `raw_text`) | None — no wire-shape change | Round 7 section, "artifact is still huge" |
| `gap_answers` size cap + wrong-gate/unknown-key 422s | None — this form already stays inside the new limits | the gap-answers "Backend-side note" |
| `feedback` size cap (2,000 chars) | One line: add `maxLength={2000}` to the textarea | item 7 in "Where things stand," above |

**The one item with real product impact if skipped:** reading `final` on
`run_error`. Without it, a run that fails right after the human approved or
edited their CV still renders as a bare failure — the file is saved
server-side, but nobody looking at the screen would know that.

**Everything else here is either already covered by an existing design
(the 409 handling) or asks for nothing on this side at all** — the backend
fixes are hardening and race-condition closures, not new behavior the UI
has to represent. The two one-line items (`client_request_id`, the feedback
`maxLength`) are cheap enough to fold into whichever round next touches
`PipelineView.jsx` / `GateScreen.jsx`.

> **Frontend, 2026-10-10:** reading `final` on `run_error` is done (Round 21).
> `client_request_id` and the feedback `maxLength` are top-list items 3 and 12.

---

# Rounds 17–26 — ten small fixes, one at a time (2026-10-10)

> **Compiled 2026-10-10**, after this entry was written, with the rest of
> `src/` (top item 1). Not yet run in a browser.

Frontend lane, written by Claude on a grant to edit `frontend/src` only, one
fix per request, most critical first. **None of it has been compiled.** Each
round was checked by a diff against a pre-edit copy (session scratchpad, not
kept), bracket counts, and import/use greps. Rounds 19 and 24 were also checked
with a Python mock-up of their logic. The backend files each round relies on
were read first, not assumed. Files changed, in all: `GateScreen`,
`PipelineView`, `FinalOutput`, `RunLog`, `CvStrip`, `api.js` and `copy.js`.
`RunsView` was untouched; it picks up Round 21 through `extractFinalArtifacts`.

| Round | Change | Files | How to verify, once built |
|---|---|---|---|
| 17 | **Retired gate form.** On any 409 the buttons become "This review is no longer open…" and nothing more is sent. An accepted answer also retires the form ("Decision sent…") until `gate_done` arrives; otherwise a second click would get a 409 for its own first answer and the wording would lie. 422 while editing: "Your edit couldn't be saved: <detail>", text kept. Unreachable: "your decision wasn't sent". `ApiError` gained `.detail`. | `GateScreen`, `api.js`, `copy.js` | Approve shows "Decision sent" briefly. Replace a paused run from a second tab, then answer in the first: "review closed". |
| 18 | **Final-review reject note:** the writer doesn't read the reason yet; past the redo limit a reject ends the run unsaved. | `GateScreen`, `copy.js` | The grey note under the buttons at the final review only. |
| 19 | **Round label.** `gateKey()` (the gate name, or node + title for old logs) counts repeat `gate_wait`s. `gate.round` is set in `applyEvent`; an amber "round N · reopened with a redone version" chip; the log line gets "· round N, redone version". | `RunLog`, `PipelineView`, `GateScreen`, `copy.js` | Reject checkpoint 1: it reopens as round 2, and the log and a past run in Runs show the same. |
| 20 | **CV discard guard.** `CvStrip.discard()` never deletes the current CV's id. A byte-identical re-upload returns the current CV's own id (content hash), so Cancel or Start used to delete the CV and break the run. | `CvStrip` | Replace with the same file, then Cancel: no `DELETE` in the network tab, the CV stays. |
| 21 | **Run endings.** `outcome` / `endReason` in `applyEvent`; `run_stopped` / `run_error` clear an open gate; the end line is green, amber or red; `FinalOutput` shows a stopped or failed run's draft as amber "last draft — wasn't saved" unless `final.export` exists; `run_error.final` is read; `extractFinalArtifacts` returns `outcome`. | `PipelineView`, `FinalOutput`, `copy.js` | Replace a run paused at the final review: the review closes, the line turns amber, the CV shows as "last draft". |
| 22 | **"Request edit" → "Approve with a note"** at checkpoints 1–3, disabled until there's a note, still sending `edit`. The log line reads "approved with a note". | `GateScreen`, `RunLog`, `copy.js` | Greyed out until you type; then the run moves on. |
| 23 | **Reject note at checkpoints 1–3:** the reason isn't used; past the shared redo limit, a reject lets the run carry on. Kept general because nothing on the wire tells the browser when the limit is reached. | `GateScreen`, `copy.js` | The grey note under the buttons at checkpoints 1–3. |
| 24 | **Proxy 502.** `failure()` builds every error. A non-JSON 502 (nginx or Caddy, backend down) becomes status 0, so every "can't reach the server" sentence fires. Any other HTML error page becomes a plain sentence. | `api.js` | Stop the backend and reload: "backend unavailable" and the :8000 sentence, no HTML. |
| 25 | **Feedback label per checkpoint and mode:** run history only at 1–3; agent memory only at the final review on live runs. | `GateScreen`, `copy.js` | Demo vs live wording at the final review. |
| 26 | **CV-editor text:** "saved as a file"; live: "the lines you change are also kept in agent memory"; demo: "aren't kept". The "later runs learn" claim is dropped, because nothing reads agent memory back yet. | `GateScreen`, `copy.js` | "Edit the CV", demo vs live. |

**Found along the way, ranked at the top of this file:** items 2 (the evidence
source), 10 (404 after a restart) and 13 (stale graph dots). The backend-side
findings are written up in `backend/bugs.md` → "2026-10-10 (frontend, Rounds
17–26)".

**Mistakes made and caught in this session:** twice a new `copy.js` block landed
between a comment and the constant it describes (Rounds 23 and 25), and an edit
dropped a space (Round 18). All three were caught in the diff and fixed before
reporting.

---

# Round 27 — say that the evidence isn't the user's own (2026-10-10)

Frontend lane, top item 2. Claude made the change, on a grant to edit `frontend/`
only. **Checked by:** a diff against a pre-edit copy (session scratchpad), bracket
counts and export/import greps. **Not compiled since the change.**

**Checked in code first.** Nothing that reads evidence is owner-scoped. Profile
Search (`agents/profile.py:60`), CV Reader (`utils/cv_handling/cv_match.py`) and
the Writer (`vectordb/lookup.py`) all read the one `profile` collection. Build
Profile entries (`backend/routes/profile.py` `_index_entry`) and gate-2 answers
(`learning/profile_store.py:109`) are embedded into that same collection, with
no owner.

| Where | What it shows | Files |
|---|---|---|
| Start screen, under the CV strip | `Evidence · shared sample profile, not your own — every run reads the same sample records, plus whatever any user has added`, laid out like the `CV ·` row | `PipelineView`, `copy.js` |
| Run view, top line | `tailoring: <cv> · evidence: shared sample profile, not your own`. The line now always renders, because the evidence label applies to every run | `PipelineView` |
| Final review, under the change cards (only when there are changes) | amber ⚑: the records behind these changes aren't yours; check each change before approving | `GateScreen`, `copy.js` |
| Fact check note (final review and final output) | dropped "against your profile" | `copy.js` |

**How to verify, once built:**
- The idle Pipeline screen shows the Evidence row under the CV row.
- A run shows `evidence:` on its top line.
- The final review with changes shows the amber note under the cards, and
  without changes shows only "No lines were changed".

**Remove when** runs read a per-user profile (vault design P3–P4). Every
string involved is in one `copy.js` block, whose comment names the code it
rests on.

**Left open:** the seven "your profile" strings, listed under top item 2.
Closed in Round 28.

---

# Round 28 — no screen calls the shared profile "yours" (2026-10-10)

Frontend lane, the rest of top item 2. Claude made the change, on a grant to
edit `frontend/` only. **Checked by:** a diff against a pre-edit copy
(scratchpad), bracket counts, export/import greps, and a grep confirming that
"your profile" now appears only in code comments. **Not compiled since the
change.**

**Checked in code first:**
- `enrich()` (`agents/profile.py:98`) tidies a live gate-2 answer with the
  model.
- `save_gap_answers()` (`learning/profile_store.py`) writes the tidied text
  *and* the original answer to `manual_entries.json`, and embeds it into the
  shared `profile` collection. No owner is stored.
- `GET /profile/entries` returns that whole file to any signed-in user.
- `POST` and `PUT` on `/profile/entries` record no owner and check none.
- In demo mode the stored answer is the fixed stand-in, not what was typed.

| Where | Was | Now |
|---|---|---|
| Gate 2 heading | A few things your profile doesn't cover yet | …the shared profile doesn't cover yet |
| Gate 2 help | …saved to your profile, so future runs can use them | …added to the shared profile: other people's runs can use them as evidence, and anyone signed in can read them. Leave out anything private. |
| Gate 2 demo note | …saved to your profile in its place | …added to the shared profile in its place |
| Card titles (`StatePanel`) | Answers added to / Your CV, checked against **your profile** | …**the shared profile** |
| Build Profile header | answers are stored in your profile… | entries go into the shared profile every run reads — anyone signed in can see and edit them |
| Build Profile list | Your saved entries | Saved entries (everyone's, not just yours) |
| Build Profile load error | load your saved entries | load the saved entries |
| Preview panel | saves to: profile · entries in your profile: N | saves to: shared profile · saved entries, all users: N |

The Build Profile strings moved from inline into `copy.js`
(`BUILD_PROFILE_*`), per the lane's rule.

**How to verify, once built:**
- Gate 2 on a live run shows the new help line; on a demo run, the demo note too.
- The live cards for Profile Update and CV Reader carry the new titles.
- Build Profile shows the new header, list heading and preview footer.

**Change these back** when entries and answers are scoped to their owner (top
item 6, vault P3–P4).

---

# Round 29 — Start sends `client_request_id` (2026-10-10)

Frontend lane, top item 3. Claude made the change, on a grant to edit
`frontend/` only. Only `PipelineView.jsx` changed. **Checked by:**
- a diff against a pre-edit copy and bracket counts;
- a Python mock-up of the reuse rule against a model of the backend's dedupe.
  All 7 cases pass. A first version of the mock-up had a bug of its own (a
  repeated id always answered "ok"), which was caught and fixed.

**Not compiled since the change.**

**The backend's contract** (`backend/routes/runs.py` `start_run`,
`backend/runs/registry.py` `seen`/`remember`):
- the id is optional, 8–64 characters;
- only a run that *started* is remembered, keyed by (owner, id), for 10
  minutes;
- a repeated id returns that run's `run_id` and **ignores the request body**.

**What `start()` does now:**
- **One id per start, not per click.** `startRequestRef` holds `{id, jd, mode}`
  until a start succeeds. Another click with the same job description and mode
  resends the same id. So if a request reached the server but its answer was
  lost (unreachable, a proxy error), the retry gets the run that started
  instead of spending a second one.
- **A changed job description or mode gets a new id.** The backend ignores the
  body on a repeated id, so reusing it would hand back the old run for a
  request the user had changed.
- **Cleared on success.** Otherwise the next "new run" within 10 minutes would
  get the old run back.
- **A refused start (403, 409, 422) keeps its id.** That's harmless, because
  the backend remembers nothing for a refusal.
- **The id:** `crypto.randomUUID()` (36 characters) on https or localhost.
  Elsewhere, 32 hex characters from `crypto.getRandomValues`, because
  `randomUUID` doesn't exist outside a secure context (the same split as
  `clipboard.js`).

**Not covered:**
- **Two tabs** get separate ids, so the backend's one-run-per-owner rule still
  ends the first run.
- **A retry more than 10 minutes later** is a new start.
- **The start error text** for an unreachable server doesn't yet say that
  pressing Start again is safe.

**How to verify, once built:** in the network tab, `POST /api/runs` carries
`client_request_id`. Two runs started one after the other carry different ids.
Stop the backend, press Start, restart the backend, press Start again: the body
carries the same id as the failed attempt.

---

# Round 30 — Log out and "new run" ask before dropping an unsaved CV edit (2026-10-10)

Frontend lane, top item 9: the two ways Round 15 left open. Claude made the
change, on a grant to edit `frontend/` only. **Checked by:**
- a diff against pre-edit copies, bracket counts, and an export/import
  cross-check of every changed file;
- a Python mock-up of the flag's lifecycle under React's effect rules: it is
  set while an unsaved edit exists, and cleared on a save, on a return to the
  draft, and on unmount.

**Not compiled since the change.**

**Why these two weren't covered.** Logging out unmounts the whole app, and
"new run" unmounts the review. The browser's leave-page prompt fires only on a
reload or a closed tab, not on either of these.

| Change | Files |
|---|---|
| New `unsavedEdit.js`: one module-scope flag, `setUnsavedEdit` / `hasUnsavedEdit`, like `api.js`'s token. One review is open at a time, and readers only need it at the moment of a click, so nothing re-renders on it. | `unsavedEdit.js` (new) |
| `GateScreen` sets the flag in the effect that already registers the leave-page prompt, so they share one condition (`isFinal && editing && editChanged && closed !== "sent"`). The cleanup clears it. | `GateScreen` |
| **Log out** with an unsaved edit swaps the menu item for "Your edited CV isn't saved yet — logging out loses it." with **Log out anyway** / **Stay**. The confirm is a small `LogoutItem` inside the menu, so its state resets when the menu closes. | `Header`, `copy.js` |
| **"new run"** after the stream drops, with an unsaved edit, shows "Your edited CV isn't saved yet. Save it first, or discard it and start a new run." with **Discard and start over** / **Keep editing**. Saving still works there, because answers go over POST. `reset()` clears the confirm. | `PipelineView`, `copy.js` |

**Known imprecision.** If you open the "new run" confirm, press Keep editing,
save, and then press "new run" again, there's no prompt, which is correct. But
if you save while the confirm is still showing, its sentence stays until you
press one of its buttons.

**Not covered:** a central 401, and a run stopped mid-edit. Both are under top
item 9.

**How to verify, once built,** in a demo run at the final review:
- Edit the CV and change a line, then open the header menu and press Log out:
  the confirm appears. Stay keeps the edit. With no change, Log out goes
  straight through.
- With an edit open, stop the backend so the stream drops, then press "new
  run": the confirm appears. Keep editing keeps the text.

> **Changed in Round 31:** the "new run" confirm now reads "Your edited CV isn't
> saved — starting a new run discards it." and its second button is **Stay**.
> "Save it first" was wrong once the server has lost the run.
>
> **Changed in Round 32:** `setUnsavedEdit(bool)` became the
> `useUnsavedEdit(text)` hook, which holds the text and the leave-page prompt
> together. `hasUnsavedEdit()` is unchanged.

---

# Round 31 — a run the server lost says so (2026-10-10)

Frontend lane, top item 10. Claude made the change, on a grant to edit
`frontend/` only. **Checked by:**
- a diff against pre-edit copies, bracket counts, and a copy.js
  export/import cross-check;
- a Python decision table of every answer status against what the form and the
  line under the run then show.

**Not compiled since the change.**

**Checked in code first:**
- `POST /runs/{id}/gate` answers 404 "Unknown run" only when the run isn't in
  this server process's memory (`backend/routes/runs.py`).
- `registry._prune` drops *finished* runs only, so for a paused run a 404 means
  the process restarted.
- The run's log is saved by the worker's `on_finish` (`save_log`), which a
  killed process never reaches. So the run never appears in Runs, and the old
  line "reopen it from Runs once it finishes" was false there.
- `openEvents` closes on its first error, so the stream can't tell a restart
  from a blip. Only the answer's 404 can.

| Change | Files |
|---|---|
| A 404 on an answer retires the form, as a 409 does, with a third closed state `"gone"`: "This run is no longer on the server — that happens when the server restarts — so it can't continue, and this answer wasn't applied." An edit in progress stays on screen with the existing "copy it" note, and the leave-page prompt keeps guarding it. | `GateScreen`, `copy.js` |
| `answerGate` marks the run `gone` on a 404 and rethrows. The line under the run then reads "this run is no longer on the server, so it can't be finished — start a new one", with "new run" beside it, whether or not the stream had already dropped. | `PipelineView`, `copy.js` |
| The stream-lost sentence moved from inline into `copy.js` (`STREAM_LOST`). | `PipelineView`, `copy.js` |
| Round 30's "new run" confirm made neutral ("…starting a new run discards it.", **Stay**), because it also shows for a lost run, where saving can't work. | `PipelineView`, `copy.js` |

**How to verify, once built,** in a demo run paused at any checkpoint:
- Restart the backend.
- The "lost the connection" line appears.
- Press Approve: the form retires with the "no longer on the server"
  sentence, and the line below changes to "can't be finished — start a new
  one".
- At the final review with an edit open, the edit stays on screen.

---

# Round 32 — a run that ends mid-edit keeps your edit (2026-10-12)

Frontend lane, the item-9 sub-case found in Round 30. Claude made the change, on
a grant to edit `frontend/` only. Before editing, it checked that nothing in
`frontend/` had changed since Round 31. **Checked by:**
- a diff against pre-edit copies, bracket counts, and a named-import check
  across all of `src/`;
- a Python mock-up of the hand-off at the moment the run ends. React runs every
  effect cleanup before any new effect in a commit, as documented since React
  17. So the closing review releases the text first, and the ended run holds it
  second.

**Not compiled since the change.**

**The bug.** Round 21 made `run_stopped` / `run_error` clear `run.gate`, so that
a dead run's review couldn't keep live buttons. If you were editing the CV at
that moment, `GateScreen` unmounted and your text went with it. It happens when
the same user starts a run in another tab.

| Change | Files |
|---|---|
| `unsavedEdit.js` holds the edit's **text**, not a boolean. `hasUnsavedEdit()` is unchanged for `Header`. New `unsavedEditText()`. New hook `useUnsavedEdit(text)` holds the text and registers the leave-page prompt while it isn't null. `setUnsavedEdit` is gone. | `unsavedEdit.js` |
| `GateScreen` uses the hook in place of its own effect: `useUnsavedEdit(unsavedEdit ? editedText : null)`. Same condition, same prompt. | `GateScreen` |
| On `run_stopped` / `run_error`, the stream callback reads `unsavedEditText()` while the review is still mounted, and keeps it as `run.lostEdit`. `applyEvent` stays pure. | `PipelineView` |
| An ended run with `lostEdit` shows an amber box above the output: "your edited CV — not saved", with Copy and a one-line explanation. `PipelineView` holds the text with the same hook, so Log out, "new run" and a reload still ask before dropping it. | `PipelineView`, `copy.js` |
| The "new run" confirm is defined once (`resetConfirm` / `askReset`). It's now used under an ended run too, not only after a dropped stream. | `PipelineView` |

**Left in item 9:** a central 401 mid-edit.

**How to verify, once built,** in a demo run at the final review:
- Press **Edit the CV** and change a line.
- In a second tab, start another run. The first tab's review closes, and the
  amber box shows your text. Copy works.
- "new run" asks first, and so does Log out. A reload prompts.
- After "Discard and start over", nothing prompts.

---

# Round 33 — the agent graph stops pulsing when a run ends (2026-10-12)

Frontend lane, top item 13. Claude chose it over item 11 after checking that
nothing in the app can revoke a token (see item 11). Claude made the change, on
a grant to edit `frontend/` only. **Checked by:** a diff against pre-edit copies,
bracket counts, and a Python mock-up of `settle()` over six endings. All pass:
no step is left "working" or "waiting", and complete or flagged steps are
untouched.

**Not compiled since the change.**

**Checked in code first** (`backend/runs/worker.py`):
- `run_stopped` is emitted only while the run is paused at a review
  (`_wait_for_gate` returns `None`), so the stale dot was the review's pulsing
  "waiting".
- `run_error` comes from the `except` around the graph, and names no step. The
  stale dot was whichever step had a `node_start` and no `node_done`.

| Change | Files |
|---|---|
| Two new node statuses with no pulse: `stopped` (amber) and `failed` (red), matching the run's end line from Round 21. | `AgentNode` |
| `settle(statuses, cutOff)`: a step still "working" becomes `cutOff` ("failed" on `run_error`, "stopped" otherwise), and one still "waiting" becomes "stopped". | `PipelineView` |
| Applied in `applyEvent` on `run_stopped` / `run_error`, and in `answerGate` on a 404 (the run the server lost, Round 31). | `PipelineView` |

An error outside any step (in the Supervisor, or in `_close` after the graph)
leaves no step "working", so nothing changes and the red end line carries it.
Past runs in Runs draw no agent graph, so they need nothing.

**How to verify, once built:**
- Replace a run paused at any review from a second tab: that step's dot turns
  amber "stopped" and stops pulsing.
- A run that fails mid-step (for example, a missing CV file): that step turns
  red "failed".

---

# Round 34 — the review feedback box stops at the server's limit (2026-10-12)

Frontend lane, top item 12. Claude made the change, on a grant to edit
`frontend/` only. **Checked by:** a diff against pre-edit copies, bracket counts,
an import check, and the counter's thresholds (hidden below 1,800, muted up to
1,999, amber at 2,000). **Not compiled since the change.**

**Before:** the backend refuses feedback over 2,000 characters
(`GateAnswer.feedback`, `max_length=2000`), and the box had no limit. A long note
got a 422 after the user pressed a button. At the final review while editing,
`refusalText` then said "Your edit couldn't be saved: feedback: …", blaming the
edit for the note's length.

| Change | Files |
|---|---|
| `maxLength={FEEDBACK_MAX}` (2000) on the feedback box at every review. `maxLength` counts UTF-16 units and Python counts characters, so the browser is never looser than the server. | `GateScreen` |
| A count under the box from 1,800 characters (`feedbackCount`, renamed `charCount` in Round 38). At 2,000 it turns amber: "the limit: typing stops here, and a longer paste is cut to fit". The browser cuts a long paste silently, and the page can't tell whether that happened, so the text says what always happens rather than claiming a cut. | `GateScreen`, `copy.js` |

**How to verify, once built:**
- Paste about 2,500 characters into the feedback box: it stops at 2,000 and
  the amber count shows.
- Type down to under 1,800 characters: the count hides.
- Approve: no 422.

---

# Round 35 — evidence search never draws a negative score (2026-10-12)

Frontend lane, top item 17 (Round 5 item 6). Claude made the change, on a grant
to edit `frontend/` only. Only `SearchPanel.jsx` changed. **Checked by:** a diff
against a pre-edit copy, bracket counts, and the clamp's output for scores from
−1 to 1.2. **Not compiled since the change.**

**Checked in code first:**
- `POST /api/search` (`backend/routes/kb.py`) calls the store's plain `query`,
  with no reranker.
- `score = 1 − cosine distance` (`vectordb/store.py`), which runs from −1 to 1.
- So Round 5's diagnosis still holds: a hit more opposite than unrelated
  scores below 0. CSS ignores a `-40%` width, and the label read "-40 match".

| Change | Files |
|---|---|
| `matchPct(score)` caps the score to 0–100. Both the bar width and the "N match" label use it, so a negative score shows as an empty bar and "0 match". | `SearchPanel` |

**Left alone, on purpose:** `StatePanel`'s `Pct` bar has the same unclamped
width. Every value it draws is 0–1 by construction:
- `overall_fit` is a weighted sum of coverages;
- `must_have_coverage` is a ratio;
- `ats_score` is keyword hits ÷ keywords.

The schema doesn't enforce that range, though (plain `float`), so the cap
belongs there too if a score ever comes from somewhere unbounded.

**How to verify, once built:** evidence search shows bars between 0 and 100. A
negative score is rare (it needs a hit more opposite than unrelated), so the
cap mostly guards an edge.

---

# Round 36 — the final output offers both saved formats (2026-10-12)

Frontend lane, top item 14 (Round 13 item 11). Claude made the change, on a
grant to edit `frontend/` only. **Checked by:**
- a diff against pre-edit copies, bracket counts, and an import check;
- a Python decision table of eight endings against the label, buttons and
  "saved as" line each one gets.

**Not compiled since the change.**

**Checked in code first:**
- On approval, `utils/export.py` writes `<stem>.md` and a plain-text
  `<stem>.txt` (Markdown stripped), and `close_run` names both in
  `final.export`.
- `GET /runs/{id}/document?fmt=md|txt` serves either.
- The page used to offer one Download button, always `.md`.
- The route reads `final` only from `run_done`. That's item 26.

| Change | Files |
|---|---|
| A saved CV gets **Download .md** and **Download .txt**. Each fetches its own server copy under the saved file's name. With nothing saved, the single **Download** saves this page's text, as before. | `FinalOutput` |
| "saved on the server as `<stem>` (.md and .txt)" under the review status. | `FinalOutput`, `copy.js` |
| A finished run whose final review didn't approve gets an amber "last draft (not approved)" label instead of the green "final output". Round 21 covered only stopped and failed runs. Logs from before the review was recorded keep "final output". | `FinalOutput`, `copy.js` |
| A server copy that won't download saves the page's copy and says so in plain words (`finalDownloadFallback`). The sentence was inline before; it's now in `copy.js`. | `FinalOutput`, `copy.js` |

**Applies to past runs too:** `RunsView` renders the same `FinalOutput` with
the run's id.

**Not done:** Round 13's "Start a new run" offer. Pipeline already shows "new
run" right under the output.

**How to verify, once built:**
- **An approved demo run:** two download buttons. Each file arrives under its
  saved name, and the .txt has no Markdown. The "saved on the server as …"
  line shows.
- **A run rejected at the revision limit:** amber "last draft (not approved)",
  and one Download.
- **The same, opened from Runs:** it looks the same.

---

# Round 37 — the final review's changes are readable (2026-10-12)

Frontend lane, top item 15 (Round 13 item 9). Claude made the change, on a grant
to edit `frontend/` only. **Checked by:**
- a diff against pre-edit copies, bracket counts, and a named and default
  import check across all of `src/`;
- Python ports of the word diff, the grouping and the evidence map. Unchanged
  words match on both lines, each line rebuilds exactly, an over-long line is
  skipped, grouping keeps arrival order, and a record from an earlier round
  survives a redo.

**Not compiled since the change.**

**Checked in code first:**
- `final_changes` (`utils/human_gate.py`) sends `{node_id, where, before,
  after, reason, evidence_ids}`.
- `where` is "Section › Entry", or just "Section" for a loose item.
- `evidence_ids` are profile record ids, the same values `ProfileBlock.source_id`
  holds.
- Each `node_done` artifact is the step's own update (`backend/runs/worker.py`).
  Profile Search, Profile Update and the Writer each send theirs as
  `evidence: [{source_id, content, …}]`.

| Change | Files |
|---|---|
| New `ChangeList`, one file per component as the spec asks. Cards are grouped under a section heading, with the entry as a sub-heading. | `ChangeList` (new) |
| Each card labels its lines **"was"** and **"now"**. Before, the pair rested on red and green (plus a strike-through), which a red-green colour-blind reader can't tell apart. | `ChangeList`, `copy.js` |
| **Word-level highlights:** a longest-common-subsequence diff over whitespace-split words, no library. Removed words are struck through on a red tint, added ones underlined on a green tint. A line past 10,000 word pairs is shown whole. | `ChangeList` |
| **"▸ records it cites (N)"** expands each cited id with its text. An id with no text in this run shows "its text isn't among this run's records". These are shared-profile records, so the label says "records", not "your evidence". | `ChangeList`, `copy.js` |
| `PipelineView` builds the `source_id → text` map from **every** `node_done` in the run, not only the latest artifact per step, so a record from an earlier round still shows after a redo. It passes the map through `GateScreen`. | `PipelineView`, `GateScreen` |

**How to verify, once built,** at the final review of a demo run with changes:
- Cards sit under section headings.
- Each card shows "was" and "now", with only the changed words marked.
- "records it cites" opens the record texts.

---

# Round 38 — editor comfort at the final review (2026-10-13)

Frontend lane, top item 16 (Round 13 item 10), the last 🟡 this folder can fix
alone. Claude made the change, on a grant to edit `frontend/` only. Before
editing, it checked that nothing in `frontend/` had changed since Round 37.
**Checked by:**
- a diff against pre-edit copies, bracket counts, and a named and default
  import check across `src/` (no `feedbackCount` left);
- a Python port of the preview's line rules on `render_markdown`-shaped text,
  and the count's thresholds.

**Not compiled since the change.**

**Checked in code first:** `render_markdown` (`utils/cv_handling/cv_edit.py`)
writes:
- `# ` the name, with the header's other lines joined by Markdown's two-space
  line break;
- `## ` a section and `### ` an entry;
- `- ` a line, and `- **Label:** a | b` for a skills group.

| Change | Files |
|---|---|
| New `MarkdownPreview`: a read-only reading view handling exactly those forms, plus `**bold**`. Everything else shows as plain text. It builds elements, never `innerHTML`, so typed markup stays text. A one-line note above it says it isn't the PDF's layout. | `MarkdownPreview` (new), `copy.js` |
| An editor toolbar: **Preview / Edit**; **Reset to the draft** with an inline "Put the draft back?" confirm (Reset / Keep my edits), enabled by any difference from the draft so a cleared editor can be refilled; and a character count, muted, amber from 45,000, with the limit sentence at 50,000. Cancel also clears the new states. | `GateScreen`, `copy.js` |
| `FINAL_EDIT_MAX` replaces the bare `50000` in the textarea's `maxLength`. Round 34's `feedbackCount` became the general `charCount` (with thousands separators), shared by both boxes. | `GateScreen`, `copy.js` |

**How to verify, once built,** at a demo run's final review, after pressing
**Edit the CV**:
- Preview shows headings, bullets and bold skills labels; Edit returns to the
  text.
- Change a line: Reset asks, Keep my edits keeps the text, and Reset restores
  the draft.
- Paste past 45,000 characters: the count turns amber.

---

# Round 39 — "request more runs" tops up the same account (2026-10-13)

Frontend lane, top item 27. The backend's identity work broke this flow, and
the backend's own `request_more` docstring flagged it. Claude made the change,
on a grant to edit `frontend/` only. **Checked by:**
- a diff against pre-edit copies, bracket counts, and a named and default
  import check across `src/`;
- a check that every `useAuth()` destructure names a value the provider
  supplies. `requestAccess` is now used only by `LoginScreen`, as intended.

**Not compiled since the change.**

**Checked in code first** (`backend/routes/auth.py`, `backend/auth/store.py`):
- `POST /auth/request-access` files a **signup**. Approving one for a name
  that already has an account fails: `approve_request` → `create_profile`
  raises, and the route answers 409. That's what Account was calling.
- `POST /auth/request-more {note}` (authenticated) files a `topup` from the
  caller's own token. On approval it adds `DEFAULT_RUN_ALLOWANCE` to that
  **same** token, mints nothing, and returns the record without a token.
- A second pending top-up from the same token is a 400 with a plain reason.
- `AdminPanel` shows a token only `if (res.token)`, so approving a top-up
  correctly shows none. It needed no change.

| Change | Files |
|---|---|
| New `requestMore(note)` in `AuthContext`, posting `/auth/request-more`. `requestAccess` stays for the sign-in page. Comments say which is which, and why. | `AuthContext` |
| Account's "Request more runs" calls `requestMore`. An error shows the server's own reason (`err.detail`), such as "a top-up request for your account is already awaiting review". | `Account` |
| Both sentences rewritten (`TOPUP_HELP`, `TOPUP_SENT`). The old ones said an admin would "issue you a new token — sign in with it", and "the same request as the sign-in page". Neither is true for a top-up. | `Account`, `copy.js` |
| Account calls `refresh()` (re-reads `/auth/me`) each time it opens, so approved runs show there and in the header. A changed count clears an old "request sent". | `Account` |
| Pipeline's 403 on Start now reads "No runs left — request more from Account." (`NO_RUNS_LEFT`) instead of "ask an admin to issue a new one". The inline string moved to `copy.js`. | `PipelineView`, `copy.js` |

**Nothing new needed from the backend:** `backend/context.md` §D's line for
this was marked done.

**How to verify, once built:**
- Sign in as a user with 0 runs and open Account. "Request more runs" sends
  `POST /api/auth/request-more`; the network tab shows it.
- Press it again after a reload: the plain "already awaiting review" sentence.
- As admin, approve the top-up. No token panel appears.
- Back as the user, reopen Account: the runs show, and the box is gone.

---

# Round 40 — Build Profile says who can see what, per role (2026-10-13)

Frontend lane, top item 28. The backend's owner scope made Round 28's wording
false. Claude made the change, on a grant to edit `frontend/` only. **Checked
by:**
- a diff against pre-edit copies, bracket counts, and a named and default
  import check across `src/`;
- a grep confirming none of the three false phrases is left in `copy.js`.

**Not compiled since the change.**

**Checked in code first** (`backend/routes/profile.py`):
- `POST /profile/entries` stamps `owner = scope.profile_id`.
- `visible_entries` shows a user only their own entries, and shows the admin
  all of them.
- A non-owner `PUT` is 403 "Not your entry"; the admin can edit any entry.
- Ownerless entries are admin-only. Gate-2 answers are ownerless, because
  `learning/profile_store` stamps none.
- `_index_entry` still embeds every entry into the one shared `profile`
  collection, and `/search` is unscoped.

| Change | Files |
|---|---|
| **Role-aware wording.** A user reads `BUILD_PROFILE_HELP` ("only you and an admin can see and edit your entries here — but every run reads them, and evidence search can find them"), "Your saved entries" and "your saved entries: N". The admin reads `_ADMIN` variants ("every account's"). `BUILD_PROFILE_SAVES_TO` now says "your entries, and the shared evidence pool". | `copy.js`, `BuildProfile`, `PreviewPanel` |
| **The gate-2 answers note** (`BUILD_PROFILE_GAP_NOTE`), users only, with or without a list: "Answers you give at the second checkpoint don't appear here yet — they aren't linked to your account." | `BuildProfile`, `copy.js` |
| **A 403 on save** shows `BUILD_PROFILE_NOT_YOURS` ("This entry isn't yours, so it wasn't changed.") instead of "403 Not your entry". It takes a stale list to reach. | `BuildProfile`, `copy.js` |
| **`GAP_HELP`'s code comment** is corrected. Its claim ("anyone signed in can read them") is still true, but through the unscoped evidence search, not `GET /profile/entries`, which is now owner-scoped. The on-screen text is unchanged. | `copy.js` |

**What would make these strings false:**
- the gate-2 note: `save_gap_answers` stamping an owner;
- the second half of the help: retrieval or `/search` scoping (vault P3–P4).

Both are recorded in `backend/context.md` §A.

**How to verify, once built:**
- As a user, Build Profile shows the user help text, "Your saved entries" and
  the gate-2 note.
- As admin, it shows "every account's" and no note.
- Saving still works for both.

---

# Round 41 — the gate-2 answer boxes show their limit (2026-10-14)

Frontend lane, the leftover under top item 12. It was the last item this folder
could fix alone; item 1's browser half is live testing, left to the user.
Claude made the change, on a grant to edit `frontend/` only. **Checked by:**
- a diff against a pre-edit copy and bracket counts;
- a check that every `maxLength` uses a named limit, with no bare `2000`
  left;
- an import check across `src/`.

**Not compiled.** It came after the 2026-10-14 build.

**Checked in code first:** each gate-2 answer is still capped at 2,000
characters by the backend (`GapText` in `backend/routes/runs.py`). The boxes
had `maxLength={2000}` but no count. So a paste longer than that was cut to
fit without a word, the same problem Round 34 fixed for the feedback box.

| Change | Files |
|---|---|
| `GAP_ANSWER_MAX` (2,000) replaces the bare `maxLength={2000}` on each gate-2 answer box, with a comment naming the backend cap. | `GateScreen` |
| Each box shows the shared `charCount` from 1,800 characters, muted, and amber at 2,000 with "the limit: typing stops here, and a longer paste is cut to fit". It's the same rule and wording as the feedback box. | `GateScreen` |

**How to verify, once built:** at a run's second checkpoint, paste about 2,500
characters into one answer box. It stops at 2,000, and the amber count shows
under that box only.

---

# Round 42 — a dead token is noticed (2026-10-14)

Frontend lane, top item 11 (Round 5 item 7). It had been ranked down because
nothing in the app can revoke a token. It was the last code item this folder
could fix alone, since item 1's browser half is left to the user. Claude made
the change, on a grant to edit `frontend/` only. **Checked by:**
- a diff against pre-edit copies and bracket counts;
- a check that `endSession` is defined after `apply`, which it calls, and
  before its two users;
- an import check across `src/`;
- a table of what `refresh()` does per outcome.

**Not compiled.** It came after the 2026-10-14 builds.

**Checked in code first:**
- The backend answers 401 only for a missing, malformed or unknown token, and
  never for "wrong role", "not yours" or "out of runs" (`backend/deps.py`). So
  a 401 on `/auth/me` means the token is gone.
- A token can still die without a revoke route: `ADMIN_TOKEN` rotated, or
  `tokens.json` edited.
- `api.js` exempts `/auth/me` from the central handler (`NO_GLOBAL_401`),
  because it's also the boot probe. And `refresh()` caught every error with
  `.catch(() => {})`. So the 401 was swallowed twice, and the runs counter
  just froze.
- `EventSource` can't see a status, so over the stream a dead token read as
  "lost the connection to this run".

| Change | Files |
|---|---|
| The central handler's two lines (clear the session, set `sessionEnded`) became `endSession()`, shared by the handler and `refresh()`. | `AuthContext` |
| `refresh()` calls `endSession()` on a 401 only. Unreachable, a proxy 502, a 5xx or a 404 still leave the session alone. The boot probe `check()` is separate and unchanged. | `AuthContext` |
| When the live stream drops, `PipelineView` also calls `refresh()` once, as the probe Round 5 asked for. A 401 ends the session; otherwise "lost the connection" stands. It also fires when a finished run's stream closes, which is harmless: it just refreshes the counter. | `PipelineView` |

**Known, and unchanged:** a session ended this way during an unsaved
final-review edit loses the edit, as any central 401 does. That's top item 9's
last case, which waits on Resume.

**Limit:** `openEvents` closes the stream on its first error and never
reconnects, so the probe runs once, when the stream drops. If the backend is
down at that moment (a restart), the probe gets status 0 and does nothing. The
next real call's 401 then ends the session centrally.

**How to verify, once built:**
- Sign in as a user and change that token's value in `tokens.json`.
- Open Account: the app goes to the sign-in screen with "your session ended".
- Change the token again while a run streams, and let the run reach its end.
  When the stream closes, the probe's 401 ends the session the same way.

# Round 43 — Resume a run the server restarted under (2026-10-15)

Closes the frontend half of top items 10 and 21. Round 31's wording ("can't be
finished — start a new one") had been false since the backend's restart
survival (2026-10-13).

**Checked in code first (backend, unchanged):** `POST /runs/{id}/resume`
(`routes/runs.py`) → `registry.resume`: 404 unknown, 403 not yours, 409 when
a worker already holds the run, another of your runs is active, or it isn't
parked at a gate; never charges a run. `GET /runs`'s `interrupted` is true only
for a gate-parked run with no live worker. The events route replays the whole
saved trail, ending in the open `gate_wait`, so a fresh fold reopens the same
review (same `ts`).

| Change | Files |
|---|---|
| `resumeRun(id)`: reads the run's row from `GET /runs`; POSTs `…/resume` only when `interrupted`; then reconnects with a fresh fold (`openStream`, factored out of `start`). Not interrupted means the server still holds it (a network blip), so reconnecting is enough. | `PipelineView` |
| A **Resume** button on the line under a run whose stream dropped or whose answer 404'd. A refusal shows the server's reason (`RESUME_FAILED`). | `PipelineView`, `copy.js` |
| An unsaved final-review edit of the **same** run survives the Resume: kept by the open review's `ts`, handed back to the reopened review, which opens in the editor (`restoredEdit`). Resuming a **different** run over an unsaved edit is refused with `RESUME_UNSAVED_EDIT`. | `PipelineView`, `GateScreen`, `copy.js` |
| Runs: an interrupted row says "interrupted" (amber); opening it shows `RUNS_INTERRUPTED_HELP` and a Resume button, which switches to Pipeline and resumes there (`App`'s `resumeRequest`). Not a button inside the row: the row is already one. | `RunsView`, `App`, `copy.js` |
| Wording: `GATE_GONE`, `RUN_GONE`, `STREAM_LOST` now point to Resume instead of saying the run is lost. | `copy.js` |

**Checked:** diff against backup (scratchpad `round43/`, not kept); bracket
balance; every new copy import exists; `PipelineView`/`RunsView`/`GateScreen`
each have exactly one caller. **Not compiled, not run.**

**Known limits:**
- A run lost before its first review has no saved log; Resume just reconnects,
  the stream fails again, and "lost the connection" comes back. `STREAM_LOST`
  says "may" for this reason.
- Clicking Resume while the server is still booting gets "cannot reach the
  backend"; click again.
- The Runs row's outcome column still uses `completed` (item 18, not this round).
- The localStorage draft (item 9's central-401 case) is still unbuilt.

**How to verify, once built (needs a yes to run):**
1. Start a run, reach any review, restart the backend. Answer → "The server
   restarted…" plus Resume. Click Resume → the same review reopens; the header's
   runs counter doesn't drop.
2. Same at the final review with an unsaved edit: after Resume the editor opens
   with your text.
3. Reload the page after a restart → Runs → the row says "interrupted" → open
   it → Resume → Pipeline shows the run at its review.
4. Resume while another of your runs is live → "Couldn't resume this run:
   Another run is already active for this owner".
5. Drop the stream without a restart (stop nginx briefly) → Resume reconnects
   without a POST.

---

## 2026-10-22 (backend) — what this session's backend work gives you, and what it asks for

> Written by the Backend API + Auth lane on a grant to add this section.
> No frontend code touched. Every item checked against `frontend/src` on
> 2026-10-22. Backend detail: `backend/bugs.md`'s 2026-10-21/22 entries.
> Tests and live runs are the owner's and are not listed here.

### A. New on the wire — additive, nothing breaks if you ignore it

| What | Where | What you can do with it |
|---|---|---|
| `run_error.node` — the agent that was running, or `null` for a failure outside a step (Supervisor, a gate, graph build) | `worker._drive` | `settle()` can mark exactly that step failed instead of inferring it from whichever was left "working" (Round 33). Keep the inference only for logs written before 2026-10-21, which have no key. This is your A2 ask |
| `node_done.unchanged: true`, **and no `artifact` key**, when a node ran and changed nothing (`cv_link` skipping a re-read on a gate-3 loop-back, `profile_enrich` with no answers) | `worker._drain_stream` | `PipelineView.jsx:75`'s `rereadSkipped` can become one generic rule: keep the previous artifact when `ev.unchanged`. Checked against your code first — the current special case still fires with the key absent, `StatePanel.jsx:260` hides a card whose artifact is falsy, and `renderArtifact` already answers "no output yet", so nothing breaks before you change it |
| `GET /api/me/export` → `application/zip` of the caller's own account (identity, Build-Profile entries, CV index + PDFs, full run trails, saved CVs, own audit log) | new `backend/routes/me.py` | an Account-page "Download my data" button. `413` if the account's data exceeds 64 MB; `401` unauthenticated |
| `GET /api/kb/claim_boundaries/do_not_claim` now returns **22 records**, not one wrapper | `routes/kb.py:_records` | `KnowledgeBase.jsx:32`'s `recs[0]?.forbidden_claims` unwrap is now dead code and its comment ("claim boundaries file wraps its list") is stale. The count in the browser was "3 records" (the wrapper's keys) and is now 22 |

### B. Already there — you are not blocked, the row says otherwise

- **`gate_wait` carries `revision` and `max_revisions`.** This is your B1 /
  "gate 4" §3 ask, listed as blocked on the backend. It is not:
  `utils/human_gate.py` has sent both since 2026-10-16 and the worker relays
  every payload key it does not consume (`_PAYLOAD_NOT_PASSED` excludes
  neither) — re-verified in the tree on 2026-10-22. You can build the
  "this is the last round" warning at gate 4 now.

### C. Changed error text and one new status on `POST /api/runs`

- **New `503 "No CV is configured on the server."`** when the resolved CV file
  is missing, raised *before* the allowance is spent. In practice only an
  admin with no uploaded CV sees it (the shared sample is git-ignored); a user
  with no CV still gets the same `409 "Add your CV to start a run."`.
- **The live-mode `400` text changed.** It was "Live mode needs GROQ_API_KEY in
  .env"; it now names the agents that can reach no provider and the env vars
  that would fix them, because the check became lane-aware (a run Cerebras,
  OpenRouter, Gemini or OpenAI could serve is no longer refused). If any copy
  of yours matches on that old string, it needs updating.

### D. Unchanged on purpose

Per-line CV text in `gate_wait.changes` / `line_links` stays where it is — an
explicit product decision, not an oversight. A3 (each change's cited records
inline) is **not** backend-side: `final_changes` lives in
`utils/human_gate.py`, so the ask has moved to the Agents lane's file.

## From Pipeline Infra + Config + Testing — 2026-10-23: nothing required; two notes

> Written by the Pipeline Infra lane. Not run.

- **`/api/health` gained a field, `started`** (UTC process start; bug#85.4). `Sidebar.jsx` polls `/health` into `setHealth` and shows "backend connected" from the response; an extra field changes nothing. Optional: show it as a tooltip ("backend up since …") so a stale server is visible in the UI too.
- **List rows already carry `review`, `saved`, `outcome`, `interrupted`** (`backend/runs/registry.py:list_for`); `RunsView.jsx` reads only `interrupted` and `completed` off a row. If a per-row review verdict or download link is wanted, the data is already there. Backend's comment says the UI uses `review`/`saved`; it currently does not.
- Still open and still this lane's: `frontend/nginx.conf` hardcodes `host.docker.internal:8000`, so it ignores a non-default `BACKEND_PORT` (bug#40). Harmless at the default; needs an `envsubst` template if the port is ever changed in Docker.

---

## 2026-10-23 (Agents + Orchestration, Claude) — two items from this session's gate and Document work

Nothing in `frontend/` was edited. One of these changes what a screen is *for*;
the other is a payload key that now exists.

**N1 🟠 The gate-4 reject reason is now load-bearing: it drives the rewrite.**
Until today, a gate-4 reject produced a near-identical CV — `document.node` read
neither `critique` nor `gate_feedback`, so the redo rebuilt a byte-identical
prompt (bug#76 item 1, bug#55 item 1). That is fixed: on a redo round every
writer packet now carries a `REVISION NOTES` block built from the Critic's
findings, the fact-checker's findings, and **the `feedback` text of the most
recent gate-4 reject** — the only one of the three a person wrote.

What this asks of the screen: a reject at the final review should **require, or
at least strongly prompt for, a reason**, and the copy should say what it is for
— that sentence is handed to the Writer and is what the next draft is written
against. If the form lets someone reject with an empty `feedback`, the redo falls
back to "(no specific finding was recorded; improve the listed lines further)" and
the candidate gets back a draft that looks much like the one they rejected, which
is exactly the complaint bug#55 item 1 recorded from a UI run.

Gates 1-3 are unaffected: their rejects loop back to an earlier agent and never
pass through Document, and the gate deliberately carries only a gate-4 reject's
reason.

**N2 ⚪ A re-opened gate's payload can carry an `error` string.**
Since bug#82 the gate re-asks instead of raising when an answer cannot be used,
and bug#74 item 4 widened what counts: a non-dict answer, a missing or invalid
`decision`, or a non-dict `edited_payload` / `gap_answers`. When that happens the
same payload comes back with one extra key, `error`, naming what was wrong.
`worker._park` forwards it like any other payload key, so it already reaches
`gate_wait` with no backend change.

Your path almost certainly cannot trigger it — `GateAnswer` types all three
fields and a bad one is a 422 before the graph sees it — so this is a line for
completeness, not a task. If you ever do render it, the gate otherwise looks
identical to its first opening, which would be the confusing part.

(Still outstanding from 2026-10-22, already logged here as N1 on that date: the
gate-4 form must render `standing_verdict`, or the key is carried and ignored.
Unrelated to the two items above.)

## From KB + Semantic Search + RAG — 2026-10-23: nothing required; one thing you may see

> No `frontend/` code edited, nothing run.

- **The KB browser's vector counts may briefly list extra collections** named
  `profile__staging`, `profile__old` and the same for `documents` and `learning`,
  while a rebuild runs or after one crashes. That comes from `GET /api/kb`
  (Backend item KB-1 in `backend/bugs.md`, which should filter them). Until then,
  render only the three real names if you want to be safe.
- **No score from hybrid retrieval is shown anywhere**: `/api/search` uses
  semantic `query`, so audit #4's change to hybrid scores does not reach the UI.

---

## 2026-10-24 (frontend, Round 44) — first full browser pass, three copy/config fixes

**Who:** Frontend test pass (Claude), user-granted run-and-fix scope. **How:** `docker build` (63 modules,
237.52 kB, Round 43 compiles), `scripts/dev.py up --docker --offline`, the built-in browser at
`http://localhost:3000`, account `uitest-20261024-142001`. Step-by-step results:
`context/testing/frontend/results.md`.

**Closed:**
- Top item 1 (never run in a browser) — every screen except Admin and the CV file picker ran.
- N2 — `GAP_DEMO_NOTE` reworded (DEC-161).

**Changed (Round 44):**
- `copy.js:GAP_DEMO_NOTE` — demo answers stay in the run, nothing saved (DEC-161).
- `copy.js:FINAL_REJECT_NOTE` — the reason is now read by the writer, so the note asks for one (DEC-162).
- Backend, outside this folder: `/api/config` lists all five providers, so Settings no longer shows the
  Cerebras/OpenRouter agents as unbacked (DEC-163).

**New open items (also bug#119):**
- 🟠 **Phone layout:** the `w-52` sidebar never collapses; at 375 px the main column is clipped and scrolls
  sideways (`Sidebar.jsx:25`).
- 🟡 **Gate 4 accepts an empty reject reason** (Agents N1 of 2026-10-23); the wording now warns, the form
  doesn't require it.
- 🟡 **No delete for Build Profile entries** (backend has no DELETE route). Test entry `35c2f0b5` is still in
  the shared pool.
- 🟡 **Settings shows raw names** for `supervisor`, `document_plan`, `query_refine`, `rerank_critic`,
  `rank_refiner`, `rank_verifier`.
- ⚪ "adding another projects entry" wording in Build Profile.

**Still open, unchanged:** N1 (`standing_verdict` not rendered — the key does arrive, `{}` in a demo run).

**Not covered:** CV upload picker (the built-in browser can't choose files), Admin panel, "request more runs",
the `interrupted` row in Runs.

