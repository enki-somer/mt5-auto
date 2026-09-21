from __future__ import annotations

from app.updater import UpdateAction, plan_update, relaunch_command, requirements_touched


def test_plan_stays_put_when_shas_match() -> None:
    plan = plan_update(
        startup_sha="aaa",
        head_sha="aaa",
        remote_sha="aaa",
        dirty=False,
        can_fast_forward=True,
    )
    assert plan.action is UpdateAction.NONE
    assert plan.detail == "current"


def test_plan_restarts_when_local_commit_moves() -> None:
    plan = plan_update(
        startup_sha="aaa",
        head_sha="bbb",
        remote_sha="bbb",
        dirty=False,
        can_fast_forward=True,
    )
    assert plan.action is UpdateAction.RESTART


def test_plan_pulls_when_github_is_ahead() -> None:
    plan = plan_update(
        startup_sha="aaa",
        head_sha="aaa",
        remote_sha="ccc",
        dirty=False,
        can_fast_forward=True,
    )
    assert plan.action is UpdateAction.PULL
    assert plan.detail == "remote-ahead"


def test_plan_skips_dirty_or_diverged_history() -> None:
    dirty = plan_update(
        startup_sha="aaa",
        head_sha="aaa",
        remote_sha="ccc",
        dirty=True,
        can_fast_forward=True,
    )
    diverged = plan_update(
        startup_sha="aaa",
        head_sha="aaa",
        remote_sha="ccc",
        dirty=False,
        can_fast_forward=False,
    )
    assert dirty.detail == "dirty"
    assert diverged.detail == "diverged"
    assert dirty.action is UpdateAction.NONE
    assert diverged.action is UpdateAction.NONE


def test_requirements_touch_detects_only_the_requirements_file() -> None:
    assert requirements_touched(["app/gui/app.py", "requirements.txt"])
    assert not requirements_touched(["app/updater.py"])


def test_relaunch_uses_the_module_when_not_frozen() -> None:
    command = relaunch_command("app.gui")
    assert command[-2:] == ["-m", "app.gui"]
