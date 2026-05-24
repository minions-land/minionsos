import { Component, ErrorInfo, ReactNode } from "react";

/**
 * React error boundary for VIZ tab views.
 *
 * Without this, an exception inside DraftView / LibraryView (e.g. malformed
 * draft.json on a fresh project, an unguarded null deref, or a force-sim
 * NaN cascade) unmounts the whole React tree and leaves the bottom-dock
 * tab buttons unresponsive — the symptom the user reported as "click Draft,
 * page crashes, then Universe button is locked".
 *
 * Each tab gets its own boundary so a crash in one view doesn't affect the
 * others, and the error UI shows a Retry button that resets the boundary
 * state so the user can attempt the view again after the underlying data
 * has been refetched.
 */
interface Props {
  /** Short label shown in the error UI ("Draft", "Book", etc.). */
  view: string;
  children: ReactNode;
}

interface State {
  err: Error | null;
}

export class ViewErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { err: null };
  }

  static getDerivedStateFromError(err: Error): State {
    return { err };
  }

  componentDidCatch(err: Error, info: ErrorInfo): void {
    // eslint-disable-next-line no-console
    console.error(`[viz/${this.props.view}] render crashed:`, err, info.componentStack);
  }

  reset = (): void => {
    this.setState({ err: null });
  };

  render(): ReactNode {
    if (this.state.err) {
      return (
        <div
          style={{
            padding: 32,
            color: "var(--muted, #aaa)",
            fontFamily: "ui-monospace, SFMono-Regular, monospace",
            fontSize: 13,
            lineHeight: 1.5,
          }}
        >
          <div style={{ color: "#f87171", fontSize: 14, marginBottom: 12 }}>
            {this.props.view} view crashed
          </div>
          <div style={{ marginBottom: 16, whiteSpace: "pre-wrap" }}>
            {this.state.err.message || String(this.state.err)}
          </div>
          <button
            type="button"
            onClick={this.reset}
            style={{
              padding: "6px 14px",
              background: "transparent",
              color: "#60a5fa",
              border: "1px solid #60a5fa",
              borderRadius: 4,
              cursor: "pointer",
            }}
          >
            Retry
          </button>
          <div style={{ marginTop: 16, fontSize: 11, opacity: 0.6 }}>
            The other tabs (Universe, Tasks, Terminals, Events) are unaffected.
            Click any of them in the bottom dock to switch away from this view.
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
