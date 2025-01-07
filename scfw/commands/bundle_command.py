"""
Defines a subclass of `PackageManagerCommand` for `bundle` commands.
"""

import json
import logging
import os
import re
import subprocess
from typing import Optional

from packaging.version import InvalidVersion, Version, parse as version_parse

from scfw.command import PackageManagerCommand, UnsupportedVersionError
from scfw.ecosystem import ECOSYSTEM
from scfw.target import InstallTarget

_log = logging.getLogger(__name__)

MIN_BUNDLER_VERSION = version_parse("2.0")

_UNSUPPORTED_BUNDLER_VERSION = f"bundler before v{MIN_BUNDLER_VERSION} is not supported"

# Example output from bundle check --dry-run:
# The following gems are missing
#  * nokogiri (1.13.8)
#  * rake (13.0.6)
_MISSING_GEM_PATTERN = re.compile(r'^\s*\*\s+(\S+)\s+\(([^)]+)\)')


class BundleCommand(PackageManagerCommand):
    """
    A representation of `bundle` commands via the `PackageManagerCommand` interface.
    """
    def __init__(self, command: list[str], executable: Optional[str] = None):
        """
        Initialize a new `BundleCommand`.

        Args:
            command: A `bundle` command line.
            executable:
                Optional path to the executable to run the command. Determined by the
                environment if not given.

        Raises:
            ValueError: An invalid `bundle` command line was given.
            UnsupportedVersionError:
                An unsupported version of `bundler` was used to initialize a `BundleCommand`.
        """
        def get_executable() -> str:
            return executable if executable else "bundle"

        def get_bundler_version(executable: str) -> Version:
            try:
                bundler_version_command = [executable, "--version"]
                bundler_version = subprocess.run(bundler_version_command, check=True, text=True, capture_output=True)
                # Output format: "Bundler version 2.4.10"
                version_str = bundler_version.stdout.strip().split()[-1]
                return version_parse(version_str)
            except (IndexError, subprocess.CalledProcessError):
                raise UnsupportedVersionError(_UNSUPPORTED_BUNDLER_VERSION)
            except InvalidVersion:
                raise UnsupportedVersionError(_UNSUPPORTED_BUNDLER_VERSION)

        if not command or command[0] != "bundle":
            raise ValueError("Malformed bundle command")
        self._command = command

        self._executable = get_executable()
        if get_bundler_version(self._executable) < MIN_BUNDLER_VERSION:
            raise UnsupportedVersionError(_UNSUPPORTED_BUNDLER_VERSION)

    def run(self):
        """
        Run a `bundle` command.
        """
        subprocess.run(self._command)

    def would_install(self) -> list[InstallTarget]:
        """
        Determine the list of Ruby gems a `bundle` command would install if it were run.

        Returns:
            A `list[InstallTarget]` representing the gems the `bundle` command would
            install if it were run.

        Raises:
            ValueError: The `bundle` output did not have the required format.
        """
        # Bundler only installs or upgrades gems via the `bundle install` or `bundle update` commands
        # If neither is present, the command is automatically safe to run
        # If present with --help, a usage message is printed: nothing will be installed
        if not any(cmd in self._command for cmd in ["install", "update"]) or "--help" in self._command:
            return []

        try:
            targets = []

            if "install" in self._command:
                # For bundle install, use bundle check --dry-run to identify missing gems
                check_command = [self._executable, "check", "--dry-run"]
                check_output = subprocess.run(check_command, text=True, capture_output=True)

                # bundle check returns 1 when gems are missing
                if check_output.returncode == 1:
                    for line in check_output.stdout.splitlines():
                        if match := _MISSING_GEM_PATTERN.match(line):
                            name, version = match.groups()
                            targets.append(InstallTarget(ECOSYSTEM.BUNDLE, name, version))
            else:
                # For bundle update, use bundle outdated --parseable to identify gems that would be updated
                # First get the list of gems specified in the update command
                update_gems = []
                for i, arg in enumerate(self._command[2:]):  # Skip "bundle update"
                    if arg.startswith("-"):
                        break
                    update_gems.append(arg)

                outdated_command = [self._executable, "outdated", "--parseable"]
                if update_gems:
                    outdated_command.extend(update_gems)

                outdated_output = subprocess.run(outdated_command, check=True, text=True, capture_output=True)

                # Parse output like:
                # * rails (newest 7.0.5, installed 7.0.4, requested >= 0) in groups "default"
                for line in outdated_output.stdout.splitlines():
                    if line.startswith("*"):
                        # Extract gem name and newest version
                        parts = line.split()
                        name = parts[1]
                        newest = parts[3].rstrip(",")
                        targets.append(InstallTarget(ECOSYSTEM.BUNDLE, name, newest))

            return targets
        except subprocess.CalledProcessError:
            # An error occurred while collecting targets
            # As we can't determine what would be installed, return empty list
            _log.info("The bundle command encountered an error while collecting installation targets")
            return []
