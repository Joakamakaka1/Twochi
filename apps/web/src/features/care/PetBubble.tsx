import styles from "./PetBubble.module.css";

/**
 * The speech bubble over the pet: the place where it talks in Casa. A status region that
 * is always there, so a screen reader announces each new text. What it says
 * (GLOSSARY.md, «Bocadillo») is chooseBubble's.
 */
export function PetBubble({ text }: { text: string | null }) {
  return (
    <div role="status" className={styles.slot}>
      {text !== null && (
        // Keyed by its text, so a new one pops in instead of changing in place.
        <p key={text} className={styles.bubble}>
          {text}
        </p>
      )}
    </div>
  );
}
