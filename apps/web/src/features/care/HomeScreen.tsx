import { texts } from "../../shared";
import { homeHeadline } from "./home";
import styles from "./HomeScreen.module.css";
import { PetHome } from "./PetHome";
import { useHome } from "./useHome";

export function HomeScreen() {
  const home = useHome();
  if (home.data !== undefined && home.data.pet !== null) return <PetHome pet={home.data.pet} />;
  return (
    <div className={styles.notice}>
      {home.data !== undefined ? (
        <h1 className={styles.title}>{homeHeadline(home.data)}</h1>
      ) : !home.isError ? (
        <p>{texts.loading}</p>
      ) : (
        <>
          <p role="alert">{texts.failure}</p>
          <button type="button" onClick={() => void home.refetch()}>
            {texts.retry}
          </button>
        </>
      )}
    </div>
  );
}
