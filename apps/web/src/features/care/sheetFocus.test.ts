import { describe, expect, it } from "vitest";

import { returnFocus } from "./sheetFocus";

// The button that opened the sheet, as returnFocus sees it.
function opener(isConnected = true) {
  const focused: FocusOptions[] = [];
  return {
    isConnected,
    focused,
    focus: (options?: FocusOptions) => {
      focused.push(options ?? {});
    },
  };
}

describe("returnFocus", () => {
  it("puts focus back on the button that opened the sheet, without scrolling to it", () => {
    const button = opener();

    returnFocus(button);

    expect(button.focused).toEqual([{ preventScroll: true }]);
  });

  it("leaves focus alone when that button is no longer on the page", () => {
    const button = opener(false);

    returnFocus(button);

    expect(button.focused).toEqual([]);
  });

  it("does nothing when nothing opened the sheet", () => {
    expect(() => {
      returnFocus(null);
    }).not.toThrow();
  });
});
