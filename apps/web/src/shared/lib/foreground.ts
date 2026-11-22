/** What the page says about itself: the browser's `document` fits it. */
export interface VisibilitySource {
  readonly visibilityState: DocumentVisibilityState;
  addEventListener(type: "visibilitychange", listener: () => void): void;
  removeEventListener(type: "visibilitychange", listener: () => void): void;
}

/** Calls `back` each time the page becomes visible again; returns how to stop. */
export function onForeground(page: VisibilitySource, back: () => void): () => void {
  const listener = () => {
    if (page.visibilityState === "visible") back();
  };
  page.addEventListener("visibilitychange", listener);
  return () => {
    page.removeEventListener("visibilitychange", listener);
  };
}
