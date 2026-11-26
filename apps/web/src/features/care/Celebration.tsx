import { CELEBRATION_ICONS } from "./icons";
import styles from "./Celebration.module.css";

/**
 * The pet healed: a burst of confetti around it while it says so. Decoration only: the
 * bubble already says it. With reduced motion the confetti just appears, without moving.
 */
export function Celebration() {
  return (
    <div className={styles.burst} aria-hidden="true">
      {CELEBRATION_ICONS.map((icon, index) => (
        <span key={index} className={styles.piece}>
          {icon}
        </span>
      ))}
    </div>
  );
}
