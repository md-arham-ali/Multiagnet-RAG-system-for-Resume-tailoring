import React, { useState } from "react";
import { useAuth } from "../AuthContext.jsx";
import { hasUnsavedEdit } from "../unsavedEdit.js";
import { UNSAVED_EDIT_LOGOUT } from "../copy.js";
import Menu from "./Menu.jsx";

const itemClass =
  "w-full text-left px-3 py-1.5 text-[12px] text-[#85888f] hover:text-[#d7d9de] hover:bg-[#17191d]";

// Logging out unmounts the whole app, final review included, and the browser's
// leave-page prompt doesn't fire for that. So an unsaved CV edit gets an inline
// confirm first. Its state lives here, inside the menu, so it resets whenever
// the menu closes.
function LogoutItem({ close, logout }) {
  const [confirming, setConfirming] = useState(false);
  if (confirming)
    return (
      <div className="px-3 py-1.5 text-[12px]">
        <div className="text-[#e8b44c] mb-1.5">{UNSAVED_EDIT_LOGOUT}</div>
        <div className="flex gap-1.5">
          <button
            onClick={() => {
              close();
              logout();
            }}
            className="px-2 py-0.5 rounded border border-[#f87171]/40 text-[#f87171] hover:bg-[#f87171]/10"
          >
            Log out anyway
          </button>
          <button
            onClick={close}
            className="px-2 py-0.5 rounded border border-[#26282e] text-[#85888f] hover:text-[#d7d9de]"
          >
            Stay
          </button>
        </div>
      </div>
    );
  return (
    <button
      role="menuitem"
      onClick={() => {
        if (hasUnsavedEdit()) return setConfirming(true);
        close();
        logout();
      }}
      className={itemClass}
    >
      Log out
    </button>
  );
}

// Who you are, and how many runs you have left. Always visible.
export default function Header({ onNavigate }) {
  const { identity, logout } = useAuth();
  if (!identity) return null;

  const left = identity.runs_remaining;
  const showCounter = identity.role !== "admin" && left != null;
  const tone =
    left === 0 ? "text-[#f87171]" : left === 1 ? "text-[#e8b44c]" : "text-[#85888f]";

  return (
    <header className="h-11 shrink-0 border-b border-[#26282e] bg-[#0b0c0e] flex items-center justify-end px-6">
      <Menu
        label={
          <span>
            {identity.identifier} <span className="text-[#5c5f66]">· {identity.role}</span>
          </span>
        }
      >
        {(close) => (
          <>
            {showCounter && (
              <div className="px-3 py-1.5 text-[12px] border-b border-[#26282e]">
                <span className="text-[#5c5f66]">runs remaining </span>
                <span className={tone}>{left === 0 ? "none" : left}</span>
              </div>
            )}
            <button
              role="menuitem"
              onClick={() => {
                close();
                onNavigate("account");
              }}
              className={itemClass}
            >
              Account
            </button>
            <LogoutItem close={close} logout={logout} />
          </>
        )}
      </Menu>
    </header>
  );
}
