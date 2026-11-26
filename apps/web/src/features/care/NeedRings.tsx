import { texts } from "../../shared";
import { NEED_ICONS } from "./icons";
import type { NeedBar } from "./needBars";
import { mostUrgent } from "./needBars";
import styles from "./NeedRings.module.css";

// The ring's circle in its own 44×44 box; pathLength 100 makes the dash the value itself.
const RING = { size: 44, radius: 19, stroke: 5 } as const;
const CENTER = RING.size / 2;

/**
 * The five needs as rings that empty as the need goes down. Each one keeps a real
 * `meter` over its ring for screen readers; the needs under 30 say «la pide», and the
 * one the pet asks for most is highlighted.
 */
export function NeedRings({ bars }: { bars: readonly NeedBar[] }) {
  const urgent = mostUrgent(bars);
  return (
    <section aria-label={texts.care.needsTitle}>
      <ul className={styles.rings}>
        {bars.map((bar) => (
          <li
            key={bar.need}
            className={styles.need}
            data-asks={bar.asks || undefined}
            data-urgent={bar.need === urgent || undefined}
          >
            <span className={styles.ring}>
              <svg viewBox={`0 0 ${String(RING.size)} ${String(RING.size)}`} aria-hidden="true" className={styles.svg}>
                <circle className={styles.track} cx={CENTER} cy={CENTER} r={RING.radius} strokeWidth={RING.stroke} />
                <circle
                  className={styles.fill}
                  cx={CENTER}
                  cy={CENTER}
                  r={RING.radius}
                  strokeWidth={RING.stroke}
                  pathLength={100}
                  strokeDasharray="100"
                  strokeDashoffset={100 - bar.value}
                  transform={`rotate(-90 ${String(CENTER)} ${String(CENTER)})`}
                />
              </svg>
              <span className={styles.icon} aria-hidden="true">
                {NEED_ICONS[bar.need]}
              </span>
              <meter id={`need-${bar.need}`} className={styles.meter} min={0} max={100} value={bar.value} />
              {bar.asks && <strong className={styles.asks}>{texts.care.asksFor}</strong>}
            </span>
            <label htmlFor={`need-${bar.need}`} className={styles.name}>
              {texts.care.needs[bar.need]}
            </label>
          </li>
        ))}
      </ul>
    </section>
  );
}
