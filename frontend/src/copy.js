// Plain-language strings shown to the user, kept in one place so the wording
// stays consistent and is easy to audit against context/design.md's
// jargon-free requirement. Internal agent ids and backend field names never
// reach the screen.

// Shown when the backend flags an artifact with `stub: true` — i.e. the agent
// that produced it is still a placeholder returning fixed example output.
export const STUB_NOTE = "placeholder output — this agent is not implemented yet";

// The follow-up questions at the second checkpoint (Evidence review). They ask
// about requirements the shared profile has no record of; it isn't the user's
// own yet (EVIDENCE_SHARED, at the end of this file).
export const GAP_HEADING = "A few things the shared profile doesn't cover yet";
// Where a live answer goes: enrich() in agents/profile.py tidies it with the
// model, then save_gap_answers() in learning/profile_store.py writes the tidied
// text and the original answer to manual_entries.json and embeds it into the
// shared `profile` collection. No owner is stored. Every user's run retrieves
// from that collection, and evidence search (POST /search, unscoped) returns
// the tidied text to anyone signed in. GET /profile/entries no longer does:
// it's owner-scoped, and shows these ownerless answers to the admin only.
// Keep saying so until answers and retrieval are scoped to their owner (vault
// design P3–P4).
export const GAP_HELP =
  "Answer in your own words — anything left blank is skipped. Your answers are tidied up and added to the shared profile: other people's runs can use them as evidence, and anyone signed in can read them. Leave out anything private.";
export const GAP_REJECT_NOTE = "Rejecting discards these answers.";
// Demo mode never reads the typed text: its stand-in model returns one fixed
// answer, and that is what lands in the shared profile.
export const GAP_DEMO_NOTE =
  "Demo mode doesn't read what you type — if you answer anything, one fixed example answer stands in for it in this run only. Nothing is saved to the shared profile.";

// A checkpoint's form after it has been answered or refused. Once an answer is
// accepted, or the server says the review is no longer open (409), the form
// sends nothing more.
export const GATE_STATUS_SENT = "decision sent";
export const GATE_STATUS_CLOSED = "review closed";
export const GATE_SENT = "Decision sent — waiting for the run to pick it up.";
export const GATE_CLOSED = "This review is no longer open — the run has moved on, so this answer wasn't applied.";
// A 404 on the answer: the server process no longer holds the run. A paused run
// is never pruned (registry._prune drops finished runs only), so this means the
// server restarted. Its log is saved when a review opens (worker._persist), so
// POST /runs/{id}/resume rebuilds it at this same review, without spending a
// run (registry.resume). Pipeline's Resume, under this screen, does that.
export const GATE_GONE =
  "The server restarted and dropped this run, so this answer wasn't applied. Resume, below, picks the run back up at this review.";
export const GATE_CLOSED_EDIT_KEPT = "Your edited CV wasn't saved. It's still above — copy it if you want to keep it.";
export const GATE_UNREACHABLE = "Couldn't reach the server — your decision wasn't sent. Try again.";
export const GATE_EDIT_NOT_SAVED = "Your edit couldn't be saved:";
// A checkpoint that opened again: a reject sends the work back to the step that
// produced it, and this review reopens with that step's redone version.
export const gateReopened = (round) => `round ${round} · reopened with a redone version`;
// What a reject at checkpoints 1-3 really does today. None of the three steps
// reads the reason (only the Supervisor reads gate_feedback). The run has one
// budget of redos (max_revisions), and once it's spent decide() stops honouring
// a reject and simply moves on: the rejected version goes forward, and nothing
// on screen says so. Make this exact once gate_wait carries the round numbers.
export const GATE_REJECT_NOTE =
  "Rejecting sends this step back to be redone. It doesn't use your reason yet. Each run allows only a few redos, counted across all reviews; once they're used, rejecting here lets the run carry on with this version.";
// Checkpoints 1-3 have no edit: an "edit" there records your note and moves the
// run on exactly like Approve (utils/human_gate.py, decide() in
// agents/supervisor.py). The button says so, and still sends "edit" so the
// audit trail keeps the difference. Rename again once these gates give "edit"
// a meaning of its own.
export const GATE_APPROVE_WITH_NOTE = "Approve with a note";
export const GATE_NOTE_NEEDED = "Write your note in the feedback box first.";
// Where the feedback box's text really goes. Every answer is saved in the run's
// own history (gate_done, the run log). Only the final review's answers reach
// agent memory (utils/final_review.record_learning), and only on live runs: a
// demo run's text is fixture output and is skipped on purpose.
export const FEEDBACK_LABEL_RUN = "Feedback (saved with this run's history)";
export const FEEDBACK_LABEL_KEPT = "Feedback (saved with this run and kept in agent memory)";
export const FEEDBACK_LABEL_DEMO = "Feedback (saved with this run; demo runs aren't kept in agent memory)";
// A box's character count: under the feedback box once a note nears its limit,
// and under the CV editor always. At the limit the browser stops taking input
// and cuts a longer paste to fit, without a word. The page can't tell whether a
// paste was cut, so the text says what always happens.
export const charCount = (n, max) => {
  const count = `${n.toLocaleString()} / ${max.toLocaleString()} characters`;
  return n >= max ? `${count} — the limit: typing stops here, and a longer paste is cut to fit` : count;
};

// The final review (the last checkpoint), where the tailored CV is approved.
export const FINAL_CHANGES_HEADING = "What changed from your CV";
export const FINAL_NO_CHANGES = "No lines were changed — this is your CV as it was.";
// The two lines of a change card. Words, not only red and green, tell them
// apart, which a red-green colour-blind reader can't do from the colours.
export const CHANGE_WAS = "was";
export const CHANGE_NOW = "now";
// The records a change cites (Edit.evidence_ids), with their text from this
// run's own steps. They come from the shared profile (EVIDENCE_SHARED), so
// "records", never "your evidence".
export const changeRecords = (n) => `records it cites (${n})`;
export const CHANGE_RECORD_MISSING = "its text isn't among this run's records";
// Above the CV editor. Saved as a file on every run once approved. On live runs
// only, each changed line is also written to agent memory as a before/after pair
// (utils/final_review.record_learning) — the user's own CV text, so say so
// plainly. Nothing reads agent memory back yet, so no "later runs learn" claim.
export const FINAL_EDIT_HELP =
  "Change anything you like. Your version becomes the final CV and is saved as a file — it is not checked again. The lines you change are also kept in agent memory.";
export const FINAL_EDIT_HELP_DEMO =
  "Change anything you like. Your version becomes the final CV and is saved as a file — it is not checked again. Demo runs aren't kept in agent memory.";
export const FINAL_DISCARD_CONFIRM = "Discard your edits? The CV goes back to the draft.";
// "Reset to the draft" puts the Writer's draft back and keeps the editor open
// (Cancel closes it). It asks first, inline, like Cancel.
export const FINAL_RESET_CONFIRM = "Put the draft back? Your changes will be lost.";
// Above the editor's preview. render_markdown keeps the CV's text, not the PDF's
// styling, so the preview is a reading view, not how the file will look.
export const FINAL_PREVIEW_NOTE = "A reading view of the Markdown — not the PDF's layout.";
// Leaving the final review with an unsaved edit. Logging out and "new run" both
// unmount the review, and the browser's leave-page prompt fires only on a reload
// or a closed tab, so these two ask first, inline. No "save it first": saving
// works after a dropped connection (answers go over POST), but not once the
// server has lost the run (GATE_GONE), and this sentence shows in both cases.
export const UNSAVED_EDIT_LOGOUT = "Your edited CV isn't saved yet — logging out loses it.";
export const UNSAVED_EDIT_NEW_RUN = "Your edited CV isn't saved — starting a new run discards it.";
// What a reject at the final review really does today. Since 2026-10-23 the
// writer's redo reads the reason of the latest gate-4 reject (agents/document.py,
// REVISION NOTES; bugs_audit_fixed.md #76.1), so the note asks for one. With no
// reason the redo falls back to a generic note and comes back similar. Once the
// revision limit is reached, decide() stops honouring the reject and the run
// ends unsaved.
export const FINAL_REJECT_NOTE =
  "Rejecting asks the writer for another draft, written against your reason — say what to change, or the next draft will look much like this one. Once the revision limit is reached, rejecting ends the run without saving the CV.";
// The fact check is still a placeholder: say so instead of showing its fixed "pass".
// No "against your profile": the evidence isn't a profile of the user's own yet
// (EVIDENCE_SHARED below).
export const FACT_CHECK_PENDING =
  "Not checked yet — the fact check is a placeholder in this version, so nothing here has been verified.";
// How a run ended. run_done, run_stopped and run_error all end the stream, but
// only run_done is a finished run; the other two must not read as one.
export const RUN_DONE = "run finished — saved to the audit trail (see Runs)";
export const RUN_STOPPED = "run stopped";
export const RUN_FAILED = "run failed";
export const RUN_END_SAVED = "Everything up to that point is saved in Runs.";
// Under a run whose event stream dropped. The browser can't tell why: a network
// blip (the run goes on server-side) or a restart (it waits at its review, for
// Resume). Resume asks GET /runs which one, resumes only an `interrupted` run,
// and reconnects either way. A run lost before its first review has no saved
// log, so nothing can bring it back — hence "may".
export const STREAM_LOST = "lost the connection to this run — it may still be going. Resume reconnects to it";
// Replaces STREAM_LOST once an answer got a 404 (GATE_GONE). Resume never
// spends a run: registry.resume only picks the same run back up.
export const RUN_GONE = "the server restarted and dropped this run — Resume picks it back up at its review, without using another run";
// Resume refused by the server; its reason follows (409: another run of yours
// is active, or this one isn't waiting at a review any more).
export const RESUME_FAILED = "Couldn't resume this run:";
// Resuming a different run would replace the run on the Pipeline screen, and
// with it an edit of the CV that isn't saved. Resuming the same run keeps it.
export const RESUME_UNSAVED_EDIT =
  "Your edited CV on the Pipeline screen isn't saved — copy it, or finish that review, before resuming a different run.";
// Runs: a run waiting at a review when the server restarted (GET /runs
// `interrupted`: parked at a gate, no worker holding it).
export const RUNS_INTERRUPTED = "interrupted";
export const RUNS_INTERRUPTED_HELP =
  "This run was waiting at a review when the server restarted. Resume picks it up there, on the Pipeline screen, without using another run.";
// The draft a stopped or failed run had reached. Nothing is saved on those
// endings unless the server says so (final.export).
export const FINAL_LABEL_EARLY = "last draft";
export const FINAL_ENDED_EARLY =
  "The run ended before it finished, so this draft wasn't saved. You can still copy or download it.";
// Your own unsaved edit of the CV, kept when a stop or failure closed the final
// review under it (run_stopped / run_error clear the gate). It was never sent,
// so nothing on the server has it.
export const LOST_EDIT_HEADING = "your edited CV — not saved";
export const LOST_EDIT_HELP =
  "The run ended while you were editing, so these changes were never sent or saved. Copy them now if you want to keep them.";
export const FINAL_APPROVED = "approved at the final review — saved";
export const FINAL_APPROVED_EDITED = "approved with your edits — saved";
export const FINAL_NOT_APPROVED =
  "not approved — you rejected this draft and the revision limit was reached, so it was not saved. You can still copy or download it.";
// The card's label for a finished run whose final review didn't approve the
// draft. close_run saves only an approved CV, so this one isn't the output.
export const FINAL_LABEL_NOT_APPROVED = "last draft (not approved)";
// Where the server kept an approved CV: utils/export.py writes <stem>.md and a
// plain-text <stem>.txt (Markdown stripped), both named in final.export.
export const finalSavedAs = (stem) => `saved on the server as ${stem} (.md and .txt)`;
// A server copy that wouldn't download. This page's own text is saved in its
// place, so the user still gets the CV, and is told which copy they got.
export const finalDownloadFallback = (why) =>
  `The server's copy didn't download (${why}), so this page's copy was saved instead.`;

// Running out of runs. More come from an authenticated top-up
// (POST /auth/request-more → store.create_topup_request). Once approved, the
// runs are added to the caller's SAME token (approve_request, kind "topup"), so
// there's no new token and no new sign-in. Account re-reads /auth/me each time
// it opens, which is when approved runs show up.
export const NO_RUNS_LEFT = "No runs left — request more from Account.";
export const TOPUP_HELP =
  "Ask an admin for more runs. Once approved, they're added to this same account — no new token, no new sign-in.";
export const TOPUP_SENT =
  "Request sent. Once an admin approves it, the runs appear here — this page checks again each time you open it.";

// "Your CV": the PDF a run tailors. Wording follows the error table in
// frontend/design.md's "Your CV" addendum — never a generic "upload failed".
export const CV_NONE = "none yet";
export const CV_NEEDED = "Add your CV to start a run.";
export const CV_SAMPLE = "sample CV (not yours)";
// This server has no CV routes yet, so every run tailors the shared sample.
export const CV_UNAVAILABLE = "shared sample CV (not yours) — uploading your own isn't available on this server yet";
export const CV_READING = "reading your CV";
export const CV_CHECK_FAILED = "couldn't check which CV you have";
export const CV_PREVIEW_HEADING = "What we read";
export const CV_PREVIEW_HELP =
  "Check what was read before using this CV. If something is wrong, fix the PDF and upload it again.";
export const CV_DELETE_CONFIRM = "Delete your CV? Runs can't start until you add another.";
export const CV_ERRORS = {
  tooLarge: "This PDF is larger than 5 MB.",
  notPdf: "This file isn't a PDF.",
  no_text: "This PDF has no selectable text. It looks scanned. Export it from your editor as a text PDF.",
  no_sections: "We couldn't find CV sections (Experience, Projects, Skills…) in this PDF.",
  too_many_pages: "Keep your CV to 4 pages or fewer.",
  unreachable: "Couldn't reach the server — nothing was uploaded.",
};

// Where a run's evidence comes from: not a profile of the user's own yet. Profile
// Search (agents/profile.py), CV Reader (utils/cv_handling/cv_match.py) and the
// Writer (vectordb/lookup.py) all read the one `profile` collection. It holds the
// sample records plus every user's Build Profile entries
// (backend/routes/profile.py) and checkpoint answers (learning/profile_store.py),
// with no owner on any of them. Until runs read a per-user profile
// (backend/bugs.md, vault design P3–P4), nothing on screen may imply the
// evidence is yours; drop these strings when that lands.
export const EVIDENCE_SHARED = "shared sample profile, not your own";
export const EVIDENCE_SHARED_HELP = "every run reads the same sample records, plus whatever any user has added";
export const FINAL_EVIDENCE_SHARED =
  "The records behind these changes come from a shared sample profile and whatever any user has added — not from a profile of your own. Check each change against what you've really done before approving.";

// Build Profile, two halves that must not blur. Listing and editing are
// owner-scoped (backend/routes/profile.py visible_entries, since 2026-10-10 to
// 10-12): a user sees and edits only their own entries, a foreign PUT is 403,
// and the admin sees and can edit every account's. But every entry is still
// embedded into the one shared `profile` collection that every run's retrieval
// and evidence search read, unfiltered (_index_entry). Change the second half
// when retrieval is scoped (vault P3–P4).
export const BUILD_PROFILE_HELP =
  "only you and an admin can see and edit your entries here — but every run reads them, and evidence search can find them";
export const BUILD_PROFILE_HELP_ADMIN =
  "you see every account's entries (admin) — every run reads them, and evidence search can find them";
export const BUILD_PROFILE_SAVED = "Your saved entries";
export const BUILD_PROFILE_SAVED_ADMIN = "Saved entries, every account's (admin view)";
export const BUILD_PROFILE_SAVES_TO = "saves to: your entries, and the shared evidence pool";
export const BUILD_PROFILE_COUNT = "your saved entries:";
export const BUILD_PROFILE_COUNT_ADMIN = "saved entries, every account:";
// Gate-2 answers are written with no owner (learning/profile_store.
// save_gap_answers), and visible_entries shows ownerless entries to the admin
// only, so a user's own answers don't appear in their list. Drop this when that
// module stamps the owner.
export const BUILD_PROFILE_GAP_NOTE =
  "Answers you give at the second checkpoint don't appear here yet — they aren't linked to your account.";
// A PUT on an entry that isn't the caller's: 403 "Not your entry". A user is
// shown only their own entries, so this takes a stale list.
export const BUILD_PROFILE_NOT_YOURS = "This entry isn't yours, so it wasn't changed.";
