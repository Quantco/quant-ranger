import { useEffect, useState } from "react";

type CopyState = "copied" | "failed" | "idle";

export function useClipboard() {
  const [copyState, setCopyState] = useState<CopyState>("idle");

  useEffect(() => {
    if (copyState === "idle") return;
    const timeout = window.setTimeout(() => setCopyState("idle"), 2000);
    return () => window.clearTimeout(timeout);
  }, [copyState]);

  const copy = async (value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setCopyState("copied");
    } catch {
      setCopyState("failed");
    }
  };

  return { copy, copyState };
}

export function CopyPageLink() {
  const { copy, copyState } = useClipboard();
  const label = copyState === "copied" ? "Link copied" : copyState === "failed" ? "Could not copy link" : "Copy dashboard link";

  return (
    <button className="text-button" onClick={() => void copy(window.location.href)} type="button">
      {label}
    </button>
  );
}
