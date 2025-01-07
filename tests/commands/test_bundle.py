"""
Test utilities for bundle commands.
"""

import os
import subprocess
from typing import Optional

import pytest
from packaging.version import Version, parse as version_parse

from scfw.commands.bundle_command import BundleCommand, MIN_BUNDLER_VERSION
from scfw.ecosystem import ECOSYSTEM

from .utils import read_top_packages, select_test_install_target

TOP_BUNDLE_PACKAGES = "top_bundle_packages.txt"

# Set up test environment to use test Gemfile
TEST_DIR = os.path.dirname(os.path.realpath(__file__))
TEST_GEMFILE = os.path.join(TEST_DIR, "..", "Gemfile")
os.environ["BUNDLE_GEMFILE"] = TEST_GEMFILE

def bundle_list() -> str:
    """
    Return the current state of installed gems.
    """
    try:
        # Use bundle list to get currently installed gems
        list_output = subprocess.run(
            ["bundle", "list"],
            check=True,
            text=True,
            capture_output=True,
            env={"BUNDLE_GEMFILE": TEST_GEMFILE}
        )
        return list_output.stdout.lower()
    except subprocess.CalledProcessError:
        return ""

INIT_BUNDLE_STATE = bundle_list()
TEST_TARGET = select_test_install_target(read_top_packages(TOP_BUNDLE_PACKAGES), INIT_BUNDLE_STATE)
if not TEST_TARGET:
    raise ValueError("Unable to select target gem for testing")


def test_bundle_version_output():
    """
    Test that `bundle --version` has the required format and meets the minimum version requirement.
    """
    version_str = subprocess.run(["bundle", "--version"], check=True, text=True, capture_output=True)
    assert "Bundler version" in version_str.stdout
    version = version_parse(version_str.stdout.strip().split()[-1])
    assert version >= MIN_BUNDLER_VERSION, f"Bundler version {version} is less than required minimum {MIN_BUNDLER_VERSION}"


@pytest.mark.parametrize(
        "command_line",
        [
            ["bundle", "-h", "install"],
            ["bundle", "--help", "install"],
            ["bundle", "install", "-h"],
            ["bundle", "install", "--help"],
            ["bundle", "--version"]
        ]
)
def test_bundle_no_change(command_line: list[str]):
    """
    Backend function for testing that a `bundle` command does not encounter any
    errors and does not modify the local bundle installation state.
    """
    subprocess.run(command_line, check=True, env={"BUNDLE_GEMFILE": TEST_GEMFILE})
    assert bundle_list() == INIT_BUNDLE_STATE


@pytest.mark.parametrize(
        "command_line",
        [
            ["bundle", "check"],
            ["bundle", "check", "--dry-run"],
            ["bundle", "install", "--dry-run"],
            ["bundle", "install", "!!!nonexistent_gem_name!!!"]
        ]
)
def test_bundle_no_change_error(command_line: list[str]):
    """
    Backend function for testing that a `bundle` command raises an error and
    does not modify the local bundle installation state.
    """
    with pytest.raises(subprocess.CalledProcessError):
        subprocess.run(command_line, check=True, env={"BUNDLE_GEMFILE": TEST_GEMFILE})
    assert bundle_list() == INIT_BUNDLE_STATE


# def test_bundle_would_install_missing():
#     """
#     Test that bundle install correctly identifies missing gems.
#     """
#     command = BundleCommand(["bundle", "install"])
#     targets = command.would_install()
#     assert targets  # Should have some targets since we're using a test Gemfile
#     assert bundle_list() == INIT_BUNDLE_STATE


# def test_bundle_would_update():
#     """
#     Test that bundle update correctly identifies outdated gems.
#     """
#     command = BundleCommand(["bundle", "update"])
#     targets = command.would_install()
#     assert targets  # Should have some targets since we're using outdated gems
#     assert bundle_list() == INIT_BUNDLE_STATE


# def test_bundle_would_update_specific():
#     """
#     Test that bundle update with specific gems correctly identifies only those gems.
#     """
#     command = BundleCommand(["bundle", "update", TEST_TARGET])
#     targets = command.would_install()
#     assert len(targets) == 1
#     assert targets[0].name == TEST_TARGET
#     assert bundle_list() == INIT_BUNDLE_STATE
