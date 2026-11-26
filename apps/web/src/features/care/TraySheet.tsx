import { useEffect, useId, useRef } from "react";

import { texts } from "../../shared";
import type { ItemKey } from "../../shared";
import { returnFocus } from "./sheetFocus";
import { trayFor } from "./tray";
import type { Discovered, TrayAction } from "./tray";
import styles from "./TraySheet.module.css";

interface TraySheetProps {
  action: TrayAction;
  /** What the caretaker saw the last time they gave each item. */
  discovered: Discovered;
  /** The button that opened the sheet: focus goes back to it when the sheet goes. */
  opener: HTMLElement | null;
  onChoose: (item: ItemKey) => void;
  /** The sheet closed, with an item chosen or without. */
  onClose: () => void;
}

/**
 * The tray as a sheet that rises from the bottom: a modal `dialog`, so focus moves into
 * it when it opens and stays there. It closes without choosing with its button, Escape
 * or a tap outside it; however it goes, even removed while open, focus goes back to the
 * button that opened it.
 */
export function TraySheet({ action, discovered, opener, onChoose, onClose }: TraySheetProps) {
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    // StrictMode runs this twice: the second time the sheet is already open. Closing it in
    // a cleanup would fire `close` and shut the tray as soon as it opened.
    const sheet = dialog.current;
    if (sheet !== null && !sheet.open) sheet.showModal();
    // Every way out ends here, as closing unmounts the sheet (onClose). While the sheet
    // is still open, as in StrictMode's extra cleanup, the opener is inert and keeps none.
    return () => {
      returnFocus(opener);
    };
  }, [opener]);

  const close = () => {
    dialog.current?.close();
  };

  return (
    <dialog
      ref={dialog}
      className={styles.sheet}
      aria-labelledby={titleId}
      onClose={onClose}
      onClick={(event) => {
        // The dialog itself is only hit outside its content: on the backdrop.
        if (event.target === event.currentTarget) close();
      }}
    >
      <div className={styles.content}>
        <span className={styles.grabber} aria-hidden="true" />
        <header className={styles.header}>
          <h2 id={titleId} className={styles.title}>
            {texts.care.trays[action]}
          </h2>
          <button type="button" className={styles.close} onClick={close}>
            {texts.care.closeTray}
          </button>
        </header>
        <ul className={styles.items}>
          {trayFor(action, discovered).map((item) => (
            <li key={item.key}>
              <button
                type="button"
                className={styles.item}
                aria-label={item.label}
                onClick={() => {
                  onChoose(item.key);
                  close();
                }}
              >
                <span className={styles.itemIcon} aria-hidden="true">
                  {item.icon}
                </span>
                {item.name}
                {item.seen !== null && (
                  <span className={styles.seen} aria-hidden="true">
                    {item.seen.face}
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </dialog>
  );
}
