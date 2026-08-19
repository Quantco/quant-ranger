import { useClipboard } from "../components/Clipboard";

function CopyIcon({ copied }: { copied: boolean }) {
  return copied ? (
    <svg aria-hidden="true" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 24 24">
      <path d="m5 12 4 4L19 6" />
    </svg>
  ) : (
    <svg aria-hidden="true" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 24 24">
      <rect height="13" rx="2" width="13" x="9" y="9" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  );
}

export function CopyableRepositoryList({ label, value }: { label: string; value: string }) {
  const { copy, copyState } = useClipboard();
  const copyLabel = copyState === "copied" ? "Copied" : copyState === "failed" ? "Could not copy" : `Copy ${label.toLocaleLowerCase()} repository names`;

  return (
    <div className="repository-list-container">
      <textarea aria-label={`${label} repository names`} className="repository-list" onFocus={(event) => event.currentTarget.select()} readOnly value={value} />
      <button aria-label={copyLabel} className={`copy-button${copyState === "copied" ? " is-copied" : ""}`} onClick={() => void copy(value)} title={copyLabel} type="button">
        <CopyIcon copied={copyState === "copied"} />
      </button>
    </div>
  );
}
