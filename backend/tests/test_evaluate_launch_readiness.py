"""Tests for evaluate_launch_readiness (backend/service/utils/era_defaults.py),
the single source of truth for pre-launch gating on both call sites
(coordinator.py's real launch enforcement and the read-time
launch_blocked_reason UI signal on models/game.py and models/app.py).

Previously zero direct unit coverage: test_era_defaults.py exercises
defaults_for_era and lookup_environment_and_profile only, and
test_environments_routes.py only exercises this function indirectly through
the read-model builder, no test constructs its inputs directly and asserts
on its return value. This file tests the function itself, every branch, for
both call_site="item" and call_site="environment", using plain SimpleNamespace
stand-ins for the Environment argument since the function only ever reads
.era / .working_image_path / .installed_at off it (documented as "pure reads
of already-resolved state" in its own docstring), never a real DB row.
"""

from types import SimpleNamespace

from backend.service.utils.era_defaults import (
    CANDIDATE_EVAL_PROFILE_SENTINEL,
    evaluate_launch_readiness,
)


def _env(era="win95", working_image_path="/images/win95/working.vhd", installed_at=None):
    return SimpleNamespace(era=era, working_image_path=working_image_path, installed_at=installed_at)


# ---------------------------------------------------------------------------
# call_site="environment": only environment_not_provisioned applies here.
# environment_not_installed must never be reachable on this call site.
# ---------------------------------------------------------------------------


class TestEnvironmentCallSite:
    def test_none_environment_is_never_blocked(self):
        """A None environment argument is the CANDIDATE_EVAL_PROFILE_SENTINEL-
        style out-of-context case, structurally cannot be provisioned-checked."""
        assert evaluate_launch_readiness(call_site="environment", environment=None) is None

    def test_working_image_present_passes_regardless_of_era(self):
        env = _env(era="win98", working_image_path="/images/win98/working.vhd")
        assert evaluate_launch_readiness(call_site="environment", environment=env) is None

    def test_no_working_image_but_era_is_auto_provisionable_passes(self):
        """dos is in PROVISIONABLE_ERAS, so a missing working image is not
        blocking, it will be auto-provisioned."""
        env = _env(era="dos", working_image_path=None)
        assert evaluate_launch_readiness(call_site="environment", environment=env) is None

    def test_no_working_image_and_era_not_provisionable_blocks(self):
        env = _env(era="xbox", working_image_path=None)
        assert (
            evaluate_launch_readiness(call_site="environment", environment=env)
            == "environment_not_provisioned"
        )

    def test_environment_not_installed_never_returned_on_this_call_site(self):
        """Structural guarantee from the docstring: even an environment that
        would fail environment_is_installed must not surface
        'environment_not_installed' when call_site='environment', that check
        is not reachable on this branch at all."""
        env = _env(era="win95", working_image_path="/images/win95/working.vhd", installed_at=None)
        result = evaluate_launch_readiness(call_site="environment", environment=env)
        assert result != "environment_not_installed"
        assert result is None


# ---------------------------------------------------------------------------
# call_site="item": full gate sequence in order.
# ---------------------------------------------------------------------------


class TestItemCallSiteFullSequence:
    def test_no_profile_blocks_before_anything_else_is_checked(self):
        """profile_item_id is None short-circuits immediately, even for a
        non-PC item that would otherwise pass every other check."""
        assert (
            evaluate_launch_readiness(call_site="item", environment=None, is_pc=False, profile_item_id=None)
            == "no_profile"
        )

    def test_non_pc_item_with_profile_passes_without_any_environment_checks(self):
        """Console items (is_pc=False) never reach the environment gates at
        all, a None environment is fine as long as a profile is assigned."""
        result = evaluate_launch_readiness(
            call_site="item", environment=None, is_pc=False, profile_item_id=42,
        )
        assert result is None

    def test_pc_item_with_no_resolvable_environment_blocks(self):
        result = evaluate_launch_readiness(
            call_site="item", environment=None, is_pc=True, era="dos", profile_item_id=1,
        )
        assert result == "no_environment"

    def test_pc_item_environment_era_mismatch_blocks(self):
        env = _env(era="win98", working_image_path="/images/win98/working.vhd")
        result = evaluate_launch_readiness(
            call_site="item", environment=env, is_pc=True, era="winxp", profile_item_id=1,
        )
        assert result == "environment_era_mismatch"

    def test_pc_item_matching_era_no_working_image_non_provisionable_blocks(self):
        env = _env(era="xbox", working_image_path=None)
        result = evaluate_launch_readiness(
            call_site="item", environment=env, is_pc=True, era="xbox", profile_item_id=1,
        )
        assert result == "environment_not_provisioned"

    def test_pc_item_dos_era_always_counts_as_installed(self):
        """DOS/DOSBox-X environments have no install step, environment_is_installed
        treats era in DOS_WIN_ERAS as always installed regardless of
        installed_at, so a fresh DOS environment with no working image yet
        (auto-provisionable) and no installed_at still passes clean."""
        env = _env(era="dos", working_image_path=None, installed_at=None)
        result = evaluate_launch_readiness(
            call_site="item", environment=env, is_pc=True, era="dos", profile_item_id=1,
        )
        assert result is None

    def test_pc_item_win9x_provisioned_but_never_installed_blocks(self):
        """win95 is auto-provisionable (has a working image) but installed_at
        is still null, the OS install step was never completed."""
        env = _env(era="win95", working_image_path="/images/win95/working.vhd", installed_at=None)
        result = evaluate_launch_readiness(
            call_site="item", environment=env, is_pc=True, era="win95", profile_item_id=1,
        )
        assert result == "environment_not_installed"

    def test_pc_item_win9x_installed_passes(self):
        from datetime import datetime, timezone

        env = _env(
            era="win95",
            working_image_path="/images/win95/working.vhd",
            installed_at=datetime.now(timezone.utc),
        )
        result = evaluate_launch_readiness(
            call_site="item", environment=env, is_pc=True, era="win95", profile_item_id=1,
        )
        assert result is None

    def test_pc_item_full_happy_path_returns_none(self):
        from datetime import datetime, timezone

        env = _env(
            era="winxp",
            working_image_path="/images/winxp/working.vhd",
            installed_at=datetime.now(timezone.utc),
        )
        result = evaluate_launch_readiness(
            call_site="item", environment=env, is_pc=True, era="winxp", profile_item_id=7,
        )
        assert result is None


class TestCandidateEvalProfileSentinel:
    def test_sentinel_is_not_none_so_no_profile_check_is_skipped(self):
        """The sentinel exists precisely so a per-candidate Environment
        evaluation (e.g. one row of a platform picker) doesn't report
        no_profile for every candidate. Confirms it's treated as "a profile
        is assigned" (non-None), not resolved against a real ProfileItem."""
        env = _env(era="dos", working_image_path=None)
        result = evaluate_launch_readiness(
            call_site="item",
            environment=env,
            is_pc=True,
            era="dos",
            profile_item_id=CANDIDATE_EVAL_PROFILE_SENTINEL,
        )
        assert result is None

    def test_sentinel_value_itself_is_negative(self):
        """Regression lock: must stay outside the positive auto-increment ID
        space (see SECURITY.md) so it can never collide with a real profile id."""
        assert CANDIDATE_EVAL_PROFILE_SENTINEL < 0
