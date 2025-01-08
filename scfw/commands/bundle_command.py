"""
Defines a subclass of `PackageManagerCommand` for `bundle` commands.
"""

import json
import logging
import os
import re
import subprocess
from typing import Optional
import tempfile

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
        # Bundler installs or upgrades gems via `bundle install`, `bundle update`, or `bundle add` commands
        # If none are present, or if --help is present, or if bundle add has --skip-install,
        # the command is automatically safe to run
        if (not any(cmd in self._command for cmd in ["install", "update", "add"]) or
            "--help" in self._command or
            ("add" in self._command and "--skip-install" in self._command)):
            return []

        try:
            targets = []

            if "install" in self._command:
                # For bundle install, use bundle check --dry-run to identify missing gems
                check_command = [self._executable, "check", "--dry-run"]
                check_output = subprocess.run(check_command, text=True, capture_output=True)

                _log.debug("bundle check output: %s", check_output)

                # bundle check returns 1 when gems are missing
                if check_output.returncode == 1:
                    for line in check_output.stderr.splitlines():
                        if match := _MISSING_GEM_PATTERN.match(line):
                            name, version = match.groups()
                            _log.debug("Found missing gem: %s %s", name, version)
                            targets.append(InstallTarget(ECOSYSTEM.BUNDLE, name, version))
            elif "add" in self._command:
                # For bundle add, we make a temporary copy of the Gemfile.
                # We run bundle add on the copy with --skip-install.
                # We then check for gems that would be installed using bundle check.

                # Create a temporary directory that will be automatically cleaned up
                with tempfile.TemporaryDirectory() as tmp_dir:
                    tmp_gemfile = os.path.join(tmp_dir, "Gemfile")

                    # Copy existing Gemfile if it exists
                    if os.path.exists("Gemfile"):
                        with open("Gemfile", "r") as src, open(tmp_gemfile, "w") as dst:
                            dst.write(src.read())

                    # Set up environment with BUNDLE_GEMFILE for these specific commands
                    env = os.environ.copy()
                    env["BUNDLE_GEMFILE"] = tmp_gemfile

                    # Modify the command to use --skip-install
                    add_command = self._command.copy()
                    if "--skip-install" not in add_command:
                        add_command.append("--skip-install")

                    # Add the gem to temporary Gemfile
                    add_output = subprocess.run(add_command, env=env, check=False, capture_output=True)
                    _log.debug("bundle add output: %s", add_output)

                    # Check what would be installed using the temporary Gemfile
                    check_command = [self._executable, "check", "--dry-run"]
                    check_output = subprocess.run(check_command, env=env, text=True, capture_output=True)
                    _log.debug("bundle check output: %s", check_output)

                    if check_output.returncode == 1:
                        for line in check_output.stderr.splitlines():
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

                outdated_output = subprocess.run(outdated_command, text=True, capture_output=True)
                _log.debug("bundle outdated output: %s", outdated_output)
                # Parse output like:
                # thor (newest 1.3.2, installed 1.3.0)
                if outdated_output.returncode == 1:
                  for line in outdated_output.stdout.splitlines():
                      # Skip empty lines
                      if not line.strip():
                          continue
                      try:
                          # Extract gem name (everything before the opening parenthesis)
                          name = line.split('(')[0].strip()
                          # Extract newest version (between "newest" and ",")
                          newest = line.split('newest')[1].split(',')[0].strip()
                          targets.append(InstallTarget(ECOSYSTEM.BUNDLE, name, newest))
                      except IndexError:
                          _log.debug("Skipping malformed line: %s", line)
                          continue

            _log.debug("Found bundle targets: %s", targets)
            return targets
        except subprocess.CalledProcessError:
            # An error occurred while collecting targets
            # As we can't determine what would be installed, return empty list
            _log.info("The bundle command encountered an error while collecting installation targets")
            return []
