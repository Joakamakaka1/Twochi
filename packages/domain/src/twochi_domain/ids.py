"""Identifiers of the domain's entities, distinct types over UUID."""

from typing import NewType
from uuid import UUID

CoupleId = NewType("CoupleId", UUID)
PetId = NewType("PetId", UUID)
UserId = NewType("UserId", UUID)
