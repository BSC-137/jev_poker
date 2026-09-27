"""Legal player actions for a betting round."""

from enum import StrEnum


class Action(StrEnum):
    FOLD = "fold"
    CHECK = "check"
    CALL = "call"
    RAISE_HALF_POT = "raise_half_pot"
    RAISE_POT = "raise_pot"
    ALL_IN = "all_in"
