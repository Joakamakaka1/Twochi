/** What returnFocus needs of the button that opened a sheet. */
export interface Focusable {
  readonly isConnected: boolean;
  focus: (options?: FocusOptions) => void;
}

/**
 * Hands focus back to the button that opened a sheet once it is gone. Done by hand: the
 * dialog's own restore misses when a tap never focused the button (Safari on iOS) or
 * when the sheet is removed while open. A button that left the page is let be.
 */
export function returnFocus(opener: Focusable | null): void {
  if (opener?.isConnected === true) opener.focus({ preventScroll: true });
}
