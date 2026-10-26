import React, { useEffect, useRef, useState } from "react";

// Small popover: click outside or press Escape to close. Shared so the header
// identity menu and any future per-row action menu don't each reinvent one.
// `children` may be a function receiving close(), for items that dismiss.
export default function Menu({ label, children }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    const onKey = (e) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const close = () => setOpen(false);

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="menu"
        className="flex items-center gap-1 text-[12px] text-[#d7d9de] hover:text-white"
      >
        {label}
        <span className="text-[#5c5f66] text-[10px]">{open ? "▴" : "▾"}</span>
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 mt-2 w-52 z-30 border border-[#26282e] bg-[#131518] rounded shadow-lg py-1"
        >
          {typeof children === "function" ? children(close) : children}
        </div>
      )}
    </div>
  );
}
