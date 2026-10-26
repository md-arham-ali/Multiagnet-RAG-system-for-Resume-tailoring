import React from "react";

// Right-hand detail drawer — slides in without leaving the main view.
export default function Drawer({ title, onClose, children }) {
  return (
    <div className="fixed right-0 top-0 h-full w-[420px] bg-[#131518] border-l border-[#26282e] z-20 flex flex-col shadow-2xl">
      <div className="flex items-center justify-between px-4 py-3 border-b border-[#26282e]">
        <span className="text-[13px] text-[#d7d9de]">{title}</span>
        <button onClick={onClose} className="text-[#5c5f66] hover:text-[#d7d9de] text-[13px]">
          close ✕
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-4">{children}</div>
    </div>
  );
}
