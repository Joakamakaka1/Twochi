import styles from "./PetBubble.module.css";

/**
 * The speech bubble over the pet: the place where it talks in Casa. A status region that
 * is always there, so a screen reader announces each new text. What it says
 * (GLOSSARY.md, «Bocadillo») is chooseBubble's.
 */
export function PetBubble({ text, id }: { text: string | null; id: string }) {
  return (
    <div role="status" className={styles.slot}>
      {text !== null && (
        // Keyed by what it says and why, so a new one pops in (and is announced) instead
        // of changing in place, also the same phrase after a second outcome.
        <p key={`${id}:${text}`} className={styles.bubble}>
          {text}
        </p>
      )}
    </div>
  );
}
