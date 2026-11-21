/** One need as the API returns it, with the pet's current state already applied. */
export interface NeedReading {
  value: number;
  updated_at: string;
  rate_per_hour: number;
}

const MS_PER_HOUR = 3_600_000;

/** Value of a need at `now`, interpolated in a straight line between API reads. */
export function needValueAt(reading: NeedReading, now: Date): number {
  // A device clock behind the server means no time has passed yet.
  const elapsedMs = Math.max(now.getTime() - Date.parse(reading.updated_at), 0);
  const value = reading.value + reading.rate_per_hour * (elapsedMs / MS_PER_HOUR);
  return Math.min(100, Math.max(0, value));
}
