import { useEffect, useRef, useState, type KeyboardEvent } from "react";

type LabelledOption = { label: string };

function matchRank(label: string, query: string) {
  const candidate = label.toLocaleLowerCase();
  const search = query.trim().toLocaleLowerCase();
  if (search === "" || candidate === search) return 0;
  if (candidate.startsWith(search)) return 1;
  if (candidate.split(/[^a-zA-Z0-9]+/).some((word) => word.startsWith(search))) return 2;
  return candidate.includes(search) ? 3 : Infinity;
}

export function useAutocomplete<Option extends LabelledOption>({
  closeOnAccept = true,
  isSelectable = () => true,
  limit,
  onAccept,
  onClose,
  options,
  query,
}: {
  closeOnAccept?: boolean;
  isSelectable?: (option: Option) => boolean;
  limit?: number;
  onAccept: (option: Option) => void;
  onClose?: () => void;
  options: Option[];
  query: string;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const matches = options
    .map((option) => ({ option, rank: matchRank(option.label, query) }))
    .filter(({ rank }) => Number.isFinite(rank))
    .sort((left, right) => left.rank - right.rank)
    .map(({ option }) => option);
  const visibleOptions = limit == null ? matches : matches.slice(0, limit);
  const bestMatch = query.trim() === "" ? undefined : visibleOptions.find(isSelectable);

  const close = () => {
    setOpen(false);
    onClose?.();
  };
  const accept = (option: Option) => {
    onAccept(option);
    if (closeOnAccept) close();
  };

  useEffect(() => {
    if (!open) return;
    const closeOutside = (event: PointerEvent) => {
      if (event.target instanceof Node && !root.current?.contains(event.target)) close();
    };
    const closeOnEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    document.addEventListener("pointerdown", closeOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  const onInputKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter" && bestMatch != null) {
      event.preventDefault();
      accept(bestMatch);
      return true;
    }
    if (event.key === "ArrowDown") setOpen(true);
    return false;
  };

  return { accept, bestMatch, close, onInputKeyDown, open, root, setOpen, visibleOptions };
}
