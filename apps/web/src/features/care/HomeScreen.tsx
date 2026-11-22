import { texts } from "../../shared";
import { homeHeadline } from "./home";
import { PetHome } from "./PetHome";
import { useHome } from "./useHome";

export function HomeScreen() {
  const home = useHome();
  if (home.data !== undefined) {
    return home.data.pet === null ? <h1>{homeHeadline(home.data)}</h1> : <PetHome pet={home.data.pet} />;
  }
  if (!home.isError) return <p>{texts.loading}</p>;
  return (
    <>
      <p role="alert">{texts.failure}</p>
      <button type="button" onClick={() => void home.refetch()}>
        {texts.retry}
      </button>
    </>
  );
}
