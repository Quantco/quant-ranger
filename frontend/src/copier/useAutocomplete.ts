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
  limit,
  onAccept,
  onClose,
  options,
  query,
}: {
  closeOnAccept?: boolean;
  limit?: number;
  onAccept: (option: Option) => void;
  onClose?: () => void;
  options: Option[];
  query: string;
}) {
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const root = useRef<HTMLDivElement>(null);
  const matches = options
    .map((option) => ({ option, rank: matchRank(option.label, query) }))
    .filter(({ rank }) => Number.isFinite(rank))
    .sort((left, right) => left.rank - right.rank)
    .map(({ option }) => option);
  const visibleOptions = limit == null ? matches : matches.slice(0, limit);
  const resolvedActiveIndex = open && visibleOptions.length > 0 ? Math.min(Math.max(activeIndex, 0), visibleOptions.length - 1) : -1;
  const activeOption = resolvedActiveIndex >= 0 ? visibleOptions[resolvedActiveIndex] : undefined;

  const close = () => {
    setOpen(false);
    setActiveIndex(-1);
    onClose?.();
  };
  const accept = (option: Option) => {
    onAccept(option);
    if (closeOnAccept) close();
  };

  useEffect(() => setActiveIndex(-1), [query]);

  useEffect(() => {
    if (!open) return;
    const closeOutside = (event: PointerEvent) => {
      if (event.target instanceof Node && !root.current?.contains(event.target)) close();
    };
    const closeOnFocusOutside = (event: FocusEvent) => {
      if (event.target instanceof Node && !root.current?.contains(event.target)) close();
    };
    document.addEventListener("pointerdown", closeOutside);
    document.addEventListener("focusin", closeOnFocusOutside);
    return () => {
      document.removeEventListener("pointerdown", closeOutside);
      document.removeEventListener("focusin", closeOnFocusOutside);
    };
  }, [open]);

  const onInputKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape" && open) {
      event.preventDefault();
      close();
      return true;
    }
    if (event.key === "Enter" && activeOption != null) {
      event.preventDefault();
      accept(activeOption);
      return true;
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      setOpen(true);
      if (visibleOptions.length === 0) setActiveIndex(-1);
      else if (!open) setActiveIndex(event.key === "ArrowDown" ? 0 : visibleOptions.length - 1);
      else {
        const direction = event.key === "ArrowDown" ? 1 : -1;
        setActiveIndex((resolvedActiveIndex + direction + visibleOptions.length) % visibleOptions.length);
      }
      return true;
    }
    if (open && (event.key === "Home" || event.key === "End")) {
      event.preventDefault();
      setActiveIndex(event.key === "Home" ? 0 : visibleOptions.length - 1);
      return true;
    }
    return false;
  };

  return { accept, activeIndex: resolvedActiveIndex, close, onInputKeyDown, open, root, setActiveIndex, setOpen, visibleOptions };
}
