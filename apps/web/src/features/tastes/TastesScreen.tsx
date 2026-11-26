import { texts } from "../../shared";
import { FACES, tasteSections, tastesNotice } from "./tastes";
import styles from "./TastesScreen.module.css";
import { useRateTaste, useTastes } from "./useTastes";

// «Tus gustos»: the catalogue by kind, five faces per item. Each tap saves at once.
export function TastesScreen() {
  const tastes = useTastes();
  const rating = useRateTaste();

  if (tastes.data === undefined) {
    if (!tastes.isError) return <p>{texts.loading}</p>;
    return (
      <>
        <p role="alert">{texts.failure}</p>
        <button type="button" onClick={() => void tastes.refetch()}>
          {texts.retry}
        </button>
      </>
    );
  }

  const notice = tastesNotice(tastes.data);
  return (
    <div className={styles.screen}>
      <h1>{texts.tastes.title}</h1>
      <p className={styles.intro}>{texts.tastes.intro}</p>
      {notice !== null && <p className={styles.notice}>{notice}</p>}
      {rating.failed && <p role="alert">{texts.failure}</p>}

      {tasteSections(tastes.data.tastes).map((section) => (
        <section key={section.kind} aria-labelledby={`tastes-${section.kind}`} className={styles.section}>
          <h2 id={`tastes-${section.kind}`}>{section.title}</h2>
          <ul className={styles.items}>
            {section.items.map((item) => (
              <li key={item.key} className={styles.item}>
                <p id={`taste-${item.key}`} className={styles.name}>
                  <span aria-hidden="true" className={styles.icon}>
                    {item.icon}
                  </span>
                  {item.name}
                </p>
                <div role="group" aria-labelledby={`taste-${item.key}`} className={styles.faces}>
                  {FACES.map((face) => (
                    <button
                      key={face.affinity}
                      type="button"
                      className={styles.face}
                      aria-label={face.label}
                      aria-pressed={face.affinity === item.affinity}
                      title={face.label}
                      // Without a pet yet there is nothing to save: the list shows as it will be.
                      disabled={notice !== null}
                      onClick={() => {
                        if (face.affinity !== item.affinity) rating.rate({ item_key: item.key, affinity: face.affinity });
                      }}
                    >
                      <span aria-hidden="true">{face.icon}</span>
                    </button>
                  ))}
                </div>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
