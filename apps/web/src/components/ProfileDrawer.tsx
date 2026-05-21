import { useEffect, useRef } from "react";
import { useProfile } from "../lib/useProfile";
import { ColumnCard } from "./ColumnCard";

interface Props {
  fileId: number;
  onClose: () => void;
}

export function ProfileDrawer({ fileId, onClose }: Props): JSX.Element {
  const { state, refetch } = useProfile(fileId);
  const panelRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);

  useEffect(() => {
    previouslyFocused.current = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();

    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (e.key !== "Tab" || !panelRef.current) return;
      const focusables = panelRef.current.querySelectorAll<HTMLElement>(
        'button, a[href], [tabindex]:not([tabindex="-1"])',
      );
      if (focusables.length === 0) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      previouslyFocused.current?.focus?.();
    };
  }, [onClose]);

  return (
    <>
      <div className="pd__scrim" onClick={onClose} />
      <aside
        ref={panelRef}
        className="pd"
        role="dialog"
        aria-modal="true"
        aria-labelledby="pd-title"
      >
        <header className="pd__header">
          <h2 id="pd-title">Profile</h2>
          <button
            ref={closeRef}
            type="button"
            className="pd__close"
            onClick={onClose}
            aria-label="Close profile"
          >
            ×
          </button>
        </header>

        {state.kind === "loading" && <p className="pd__msg">Loading profile…</p>}
        {state.kind === "pending" && (
          <p className="pd__msg" aria-live="polite">
            Profiling in progress — refreshing automatically…
          </p>
        )}
        {state.kind === "error" && (
          <div className="pd__error" role="alert">
            <p>Couldn't load profile: {state.message}</p>
            <button type="button" onClick={() => void refetch()}>
              Retry
            </button>
          </div>
        )}
        {state.kind === "ready" && <ProfileBody profile={state.profile} />}
      </aside>
    </>
  );
}

function ProfileBody({
  profile,
}: {
  profile: import("../lib/useProfile").FileProfile;
}): JSX.Element {
  return (
    <div className="pd__body">
      <section className="pd__file-stats">
        <dl>
          <Stat label="Rows" value={profile.row_count.toLocaleString()} />
          <Stat label="Duplicates" value={profile.duplicate_row_count.toLocaleString()} />
          <Stat label="Encoding" value={profile.encoding} />
          <Stat label="Delimiter" value={renderDelim(profile.delimiter)} />
          <Stat label="Header?" value={profile.has_header ? "yes" : "no"} />
          <Stat label="Profile" value={`${profile.profile_version} · ${profile.profile_sha256.slice(0, 8)}…`} />
        </dl>
      </section>

      {profile.omitted_columns && profile.omitted_columns.length > 0 && (
        <p className="pd__notice">
          Wide file — {profile.omitted_columns.length} column
          {profile.omitted_columns.length === 1 ? "" : "s"} have stats omitted to
          fit the prompt budget. Listed at the bottom.
        </p>
      )}

      <section className="pd__columns">
        <h3>Columns</h3>
        {profile.columns.map((col) => (
          <ColumnCard key={col.position} column={col} />
        ))}
      </section>

      {profile.omitted_columns && profile.omitted_columns.length > 0 && (
        <section className="pd__omitted">
          <h3>Omitted columns</h3>
          <ul>
            {profile.omitted_columns.map((o) => (
              <li key={o.position}>
                <code>{o.name}</code> ({o.inferred_type}, distinct {o.distinct_count})
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="pd__stat">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function renderDelim(d: string): string {
  if (d === "\t") return "\\t";
  return d;
}
