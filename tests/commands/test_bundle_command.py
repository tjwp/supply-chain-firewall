"""
Test utilities for bundle command.
"""

import os

import pytest

from scfw.commands.bundle_command import BundleCommand
from scfw.ecosystem import ECOSYSTEM
from scfw.target import InstallTarget

from .test_bundle import INIT_BUNDLE_STATE, TEST_TARGET, bundle_list

# Set up test environment to use test Gemfile
TEST_DIR = os.path.dirname(os.path.realpath(__file__))
TEST_GEMFILE = os.path.join(TEST_DIR, "..", "Gemfile")
os.environ["BUNDLE_GEMFILE"] = TEST_GEMFILE

@pytest.mark.parametrize(
        "command_line,has_targets",
        [
            (["bundle", "install"], True),
            (["bundle", "-h", "install"], False),
            (["bundle", "--help", "install"], False),
            (["bundle", "install", "-h"], False),
            (["bundle", "install", "--help"], False),
            (["bundle", "install", "--dry-run"], False),
            (["bundle", "update"], True),
            (["bundle", "update", TEST_TARGET], True),
            (["bundle", "update", "-h"], False),
            (["bundle", "update", "--help"], False),
            (["bundle", "--non-existent-option"], False)
        ]
)
def test_bundle_command_would_install(command_line: list[str], has_targets: bool):
    """
    Test that a `BundleCommand.would_install` call either does or does not have
    install targets and does not modify the local bundle installation state.
    """
    command = BundleCommand(command_line)
    targets = command.would_install()
    if has_targets:
        assert targets
    else:
        assert not targets
    assert bundle_list() == INIT_BUNDLE_STATE


def test_bundle_command_would_install_exact():
    """
    Test that `BundleCommand.would_install` gives the right answer relative to
    missing gems that would be installed.
    """
    true_targets = list(
        map(
            lambda p: InstallTarget(ECOSYSTEM.BUNDLE, p[0], p[1]),
            [
                ("nokogiri", "1.13.8"),
                ("rake", "13.0.6")
            ]
        )
    )

    command_line = ["bundle", "install"]
    command = BundleCommand(command_line)
    targets = command.would_install()
    assert len(targets) == len(true_targets)
    assert all(target in true_targets for target in targets)


def test_bundle_command_would_update_exact():
    """
    Test that `BundleCommand.would_install` gives the right answer relative to
    outdated gems that would be updated.
    """
    true_targets = list(
        map(
            lambda p: InstallTarget(ECOSYSTEM.BUNDLE, p[0], p[1]),
            [
                ("rails", "7.0.5"),
                ("rack", "2.2.8")
            ]
        )
    )

    command_line = ["bundle", "update"]
    command = BundleCommand(command_line)
    targets = command.would_install()
    assert len(targets) == len(true_targets)
    assert all(target in true_targets for target in targets)
