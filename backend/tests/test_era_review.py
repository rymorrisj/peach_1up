"""Tests for the computed GameItemBundleRead.era_review rule
(_compute_era_review in backend/models/game.py). Pure function, no DB.

Rule: "confirmed" when the stored era_confirmed flag is true; else "verified"
when the bundle's rolled-up verification_status is "verified"; else
"unreviewed". The rule reads no detection_reason text.
"""

import pytest

from backend.models.game import _compute_era_review

_NOT_VERIFIED = ("caution", "mismatch", "not_in_index", "unchecked")


class TestComputeEraReview:
    def test_confirmed_flag_is_confirmed(self):
        assert _compute_era_review(True, "unchecked") == "confirmed"

    def test_confirmed_wins_over_verified(self):
        assert _compute_era_review(True, "verified") == "confirmed"

    @pytest.mark.parametrize("status", _NOT_VERIFIED)
    def test_confirmed_wins_over_every_weaker_status(self, status):
        assert _compute_era_review(True, status) == "confirmed"

    def test_unconfirmed_and_verified_is_verified(self):
        assert _compute_era_review(False, "verified") == "verified"

    @pytest.mark.parametrize("status", _NOT_VERIFIED)
    def test_unconfirmed_and_not_verified_is_unreviewed(self, status):
        assert _compute_era_review(False, status) == "unreviewed"
