import React, { useEffect, useRef, useState } from "react";
import { post, put } from "../api.js";
import { useFetch } from "../useFetch.js";
import Failed from "./Failed.jsx";
import SectionTracker from "./SectionTracker.jsx";
import PreviewPanel from "./PreviewPanel.jsx";
import { useAuth } from "../AuthContext.jsx";
import {
  BUILD_PROFILE_HELP, BUILD_PROFILE_HELP_ADMIN, BUILD_PROFILE_SAVED, BUILD_PROFILE_SAVED_ADMIN,
  BUILD_PROFILE_GAP_NOTE, BUILD_PROFILE_NOT_YOURS,
} from "../copy.js";

// The conversational knowledge-base feeder. One question, one answer, one
// entry. Answers build a structured record (live preview on the right); a
// confirmed entry is written to the profile store automatically.
const SECTIONS = [
  {
    id: "projects", label: "Projects",
    questions: [
      { key: "title", q: "What did you build in your last project?" },
      { key: "problem", q: "What problem did it solve?" },
      { key: "tools", q: "Which tools, languages or frameworks did you use?", list: true },
      { key: "outcome", q: "What measurable result did it produce?" },
      { key: "skills_demonstrated", q: "Which skills does this project prove?", list: true },
    ],
  },
  {
    id: "skills", label: "Skills",
    questions: [
      { key: "name", q: "Name one skill you want on record." },
      { key: "proficiency", q: "How strong are you at it — beginner, intermediate or advanced?" },
      { key: "years_of_experience", q: "How long have you used it?" },
      { key: "evidence", q: "Where have you used it — give one concrete example." },
    ],
  },
  {
    id: "achievements", label: "Achievements",
    questions: [
      { key: "title", q: "What is one achievement you are proud of?" },
      { key: "impact", q: "What changed because of it?" },
      { key: "date", q: "When was this?" },
    ],
  },
  {
    id: "education", label: "Education",
    questions: [
      { key: "institution", q: "Where did you study?" },
      { key: "degree", q: "What degree or program?" },
      { key: "end_date", q: "When did — or will — you finish?" },
      { key: "coursework", q: "Which courses mattered most?", list: true },
    ],
  },
  {
    id: "internships", label: "Internships",
    questions: [
      { key: "company", q: "Where did you intern or work?" },
      { key: "role", q: "What was your role?" },
      { key: "summary", q: "What did you actually do there?" },
      { key: "achievements", q: "What is one result you delivered?", list: true },
    ],
  },
  {
    id: "extras", label: "Extras",
    questions: [
      { key: "activity_name", q: "What do you do outside work or study?" },
      { key: "role", q: "What is your role in it?" },
      { key: "description", q: "What have you done there worth mentioning?" },
    ],
  },
];

export default function BuildProfile({ active }) {
  // The list is owner-scoped server-side: the admin gets every account's
  // entries, anyone else only their own. The wording follows (copy.js).
  const { identity } = useAuth();
  const isAdmin = identity?.role === "admin";
  const [sectionIdx, setSectionIdx] = useState(0);
  const [doneIds, setDoneIds] = useState([]);
  const [exchanges, setExchanges] = useState([]); // answered {key,q,a} for this entry
  const [editingIdx, setEditingIdx] = useState(null);
  const [entryId, setEntryId] = useState(null); // set when re-editing a saved entry
  // Entries saved in earlier sessions, not just this one. Without this the
  // edit button below only ever reached what you had typed since the last page
  // load — and editing is the only path that re-embeds a correction into the
  // profile collection, so a reload made your own entries uncorrectable.
  const { data: stored, error: loadError, reload } = useFetch("/profile/entries", { active });
  const [saved, setSaved] = useState([]);
  const [input, setInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);
  const inputRef = useRef(null);

  const section = SECTIONS[sectionIdx];
  const qIdx = editingIdx ?? exchanges.length;
  const finished = editingIdx === null && exchanges.length === section.questions.length;
  const question = finished ? null : section.questions[qIdx];

  // build the structured record from the answers so far
  const record = {};
  for (const ex of exchanges) {
    const spec = section.questions.find((s) => s.key === ex.key);
    record[ex.key] = spec?.list ? ex.a.split(",").map((s) => s.trim()).filter(Boolean) : ex.a;
  }

  useEffect(() => inputRef.current?.focus(), [qIdx, sectionIdx]);

  useEffect(() => {
    if (!stored?.entries) return;
    // Merge rather than replace: a slow fetch must not drop an entry saved
    // while it was in flight. Ours win — they are the newer copy.
    setSaved((prev) => {
      const mine = new Set(prev.map((e) => e.id));
      return [...stored.entries.filter((e) => !mine.has(e.id)), ...prev];
    });
  }, [stored]);

  const submit = () => {
    if (!input.trim()) return;
    const entry = { key: question.key, q: question.q, a: input.trim() };
    setExchanges((prev) => {
      const next = [...prev];
      if (editingIdx !== null) next[editingIdx] = entry;
      else next.push(entry);
      return next;
    });
    setEditingIdx(null);
    setInput("");
  };

  const save = async () => {
    const body = { section: section.id, record };
    setSaving(true);
    setSaveError(null);
    try {
      const res = entryId
        ? await put(`/profile/entries/${entryId}`, body)
        : await post("/profile/entries", body);
      setSaved((prev) => [...prev.filter((e) => e.id !== res.id), { ...res, section: section.id }]);
      setExchanges([]);
      setEntryId(null);
    } catch (err) {
      // Without this the form silently freezes: nothing clears, and the Save
      // button stays live as though it had never been pressed.
      setSaveError(err.status === 403 ? BUILD_PROFILE_NOT_YOURS : err.message || "could not save this entry");
    } finally {
      setSaving(false);
    }
  };

  const nextSection = () => {
    setDoneIds((d) => [...new Set([...d, section.id])]);
    setSectionIdx((i) => Math.min(i + 1, SECTIONS.length - 1));
    setExchanges([]);
    setEntryId(null);
    setEditingIdx(null);
  };

  const editSaved = (entry) => {
    const sIdx = SECTIONS.findIndex((s) => s.id === entry.section);
    // Stored entries now come from disk, so a section this build does not know
    // about is reachable — ignore the click rather than throw on SECTIONS[-1].
    if (sIdx === -1) return;
    const sec = SECTIONS[sIdx];
    setSectionIdx(sIdx);
    setExchanges(
      sec.questions
        .filter((s) => entry.record[s.key] != null)
        .map((s) => ({
          key: s.key,
          q: s.q,
          a: Array.isArray(entry.record[s.key]) ? entry.record[s.key].join(", ") : entry.record[s.key],
        }))
    );
    setEntryId(entry.id);
    setEditingIdx(null);
  };

  return (
    <div className="p-6 max-w-5xl space-y-4">
      <div className="flex items-baseline justify-between">
        <h1 className="text-[15px] text-[#d7d9de]">Build Profile</h1>
        <span className="text-[11px] text-[#5c5f66]">{isAdmin ? BUILD_PROFILE_HELP_ADMIN : BUILD_PROFILE_HELP}</span>
      </div>

      <SectionTracker sections={SECTIONS} currentIdx={sectionIdx} doneIds={doneIds} />

      <div className="grid grid-cols-[1fr_300px] gap-4 items-start">
        {/* the conversation: system asks left, you answer right; click an answer to change it */}
        <div className="border border-[#26282e] bg-[#131518] rounded p-4 space-y-3">
          {exchanges.map((ex, i) => (
            <div key={i} className={editingIdx === i ? "opacity-50" : ""}>
              <div className="text-[12px] text-[#85888f]">{ex.q}</div>
              <button
                onClick={() => { setEditingIdx(i); setInput(ex.a); }}
                title="click to edit"
                className="block ml-auto text-right text-[13px] text-[#d7d9de] hover:text-white mt-1 max-w-[85%]"
              >
                {ex.a}
              </button>
            </div>
          ))}

          {question && (
            <div>
              <div className="text-[13px] text-[#d7d9de]">{question.q}</div>
              {question.list && <div className="text-[11px] text-[#5c5f66] mt-0.5">separate with commas</div>}
              <div className="flex gap-2 mt-2">
                <input
                  ref={inputRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && submit()}
                  className="flex-1 bg-[#0b0c0e] border border-[#26282e] rounded px-2 py-1.5 text-[13px] outline-none focus:border-[#3a3d44]"
                />
                <button
                  onClick={submit}
                  disabled={!input.trim()}
                  className="px-3 rounded bg-[#d7d9de] text-[#0b0c0e] text-[13px] hover:bg-white disabled:opacity-40"
                >
                  ↵
                </button>
              </div>
            </div>
          )}

          {finished && (
            <div className="flex items-center gap-3 pt-2 border-t border-[#26282e]">
              <button
                onClick={save}
                disabled={saving}
                className="px-4 py-1.5 rounded bg-[#d7d9de] text-[#0b0c0e] text-[13px] hover:bg-white disabled:opacity-40"
              >
                {saving ? "saving…" : entryId ? "Update entry" : "Save entry"}
              </button>
              <span className="text-[11px] text-[#5c5f66]">check the preview first — click any answer to change it</span>
              {saveError && <span className="text-[11px] text-[#f87171]">{saveError}</span>}
            </div>
          )}

          {!finished && exchanges.length === 0 && saved.some((e) => e.section === section.id) && (
            <div className="text-[11px] text-[#5c5f66]">adding another {section.label.toLowerCase()} entry</div>
          )}

          {exchanges.length === 0 && (
            <div className="pt-2 border-t border-[#26282e] flex gap-3">
              {sectionIdx < SECTIONS.length - 1 && (
                <button onClick={nextSection} className="text-[12px] text-[#85888f] hover:text-[#d7d9de] underline">
                  skip to {SECTIONS[sectionIdx + 1].label} →
                </button>
              )}
            </div>
          )}
        </div>

        <PreviewPanel section={section.id} record={record} savedCount={saved.length} isAdmin={isAdmin} />
      </div>

      {loadError && (
        <Failed error={loadError} onRetry={reload} what="load the saved entries" />
      )}

      {saved.length > 0 && (
        <div className="border border-[#26282e] bg-[#131518] rounded p-3">
          <div className="text-[12px] text-[#85888f] mb-2">
            {isAdmin ? BUILD_PROFILE_SAVED_ADMIN : BUILD_PROFILE_SAVED}{" "}
            <span className="text-[#5c5f66]">· click edit to correct one</span>
          </div>
          {saved.map((e) => (
            <div key={e.id} className="flex items-center gap-3 py-0.5 text-[12px]">
              <span className="text-[#5c5f66] w-24">{e.section}</span>
              <span className="text-[#d7d9de] flex-1 truncate">
                {e.record?.title ||
                  e.record?.name ||
                  e.record?.institution ||
                  e.record?.company ||
                  e.record?.activity_name ||
                  "(untitled entry)"}
              </span>
              <button onClick={() => editSaved(e)} className="text-[#5c5f66] hover:text-[#d7d9de] underline">
                edit
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Shown with or without a list: a user looking for their checkpoint
          answers should learn why they aren't here. The admin does see them. */}
      {!isAdmin && <div className="text-[11px] text-[#5c5f66]">{BUILD_PROFILE_GAP_NOTE}</div>}
    </div>
  );
}
