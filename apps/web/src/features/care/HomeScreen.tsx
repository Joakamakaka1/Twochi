import { texts } from "../../shared";
import { homeHeadline } from "./home";
import { useHome } from "./useHome";

// For now Casa is one line: the pet in the person's care. Its rooms come with TWO-34.
export function HomeScreen() {
  const home = useHome();
  if (home.data !== undefined) return <h1>{homeHeadline(home.data)}</h1>;
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
