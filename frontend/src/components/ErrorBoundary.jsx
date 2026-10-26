import React from "react";

// The one place a class component is still required — React has no hook
// equivalent for componentDidCatch. Wrapped around each view individually so a
// throw in one panel degrades that panel instead of blanking the whole app.
export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    // Keep the stack somewhere reachable — the UI only shows the message.
    console.error(`[${this.props.name || "panel"}]`, error, info?.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="p-6 max-w-5xl">
        <div className="border border-[#f87171]/40 bg-[#131518] rounded p-4">
          <div className="text-[12px] text-[#f87171] mb-1">
            this panel hit an error{this.props.name ? ` · ${this.props.name}` : ""}
          </div>
          <p className="text-[12px] text-[#85888f] break-words">
            {this.state.error.message || String(this.state.error)}
          </p>
          <button
            onClick={() => this.setState({ error: null })}
            className="mt-3 px-3 py-1 rounded border border-[#26282e] text-[#85888f] text-[12px] hover:text-[#d7d9de] hover:border-[#3a3d44]"
          >
            try again
          </button>
        </div>
      </div>
    );
  }
}
