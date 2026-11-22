"""Who acts in a use case. The database applies RLS for them with their claims."""

from collections.abc import Mapping
from dataclasses import dataclass, field

from twochi_domain.ids import UserId


@dataclass(frozen=True, slots=True)
class UserActor:
    """A person, with the claims of their already verified token."""

    user_id: UserId
    # Out of the repr: the claims carry the email, and a repr can end up in a log.
    claims: Mapping[str, object] = field(repr=False)
