"""Hand-written doubles of the ports, one per port, for the tests.

`Database` has none: use cases are tested against local Postgres with real RLS.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class FixedClock:
    """A clock stopped at a moment the test chooses."""

    moment: datetime

    def now(self) -> datetime:
        """The moment the clock was set to."""
        return self.moment
