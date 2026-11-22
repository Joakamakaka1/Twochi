"""Who acts in a use case. The database applies RLS for them with their claims."""

from collections.abc import Mapping
from dataclasses import dataclass

from twochi_domain.ids import UserId


@dataclass(frozen=True, slots=True)
class UserActor:
    """A person, with the claims of their already verified token."""

    user_id: UserId
    claims: Mapping[str, object]
