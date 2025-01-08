"""
Defines a subclass of `PackageManagerCommand` for `gem` commands.
"""

import logging
import re
import subprocess
from typing import Optional

from packaging.version import Version, parse as version_parse

from scfw.command import PackageManagerCommand, UnsupportedVersionError
from scfw.ecosystem import ECOSYSTEM
from scfw.target import InstallTarget

_log = logging.getLogger(__name__)

MIN_GEM_VERSION = version_parse("3.0")

_UNSUPPORTED_GEM_VERSION = f"gem before v{MIN_GEM_VERSION} is not supported"

# Example output from gem --version:
# 3.4.19

# Example output from gem install --explain:
# Gems to install:
#   uri-0.13.1
#   concurrent-ruby-1.3.4
#   tzinfo-2.0.6
_INSTALL_GEM_PATTERN = re.compile(r'^\s*([a-zA-Z0-9\-_]+)-(\d+(?:\.\d+)*(?:\.pre\d*)?)')

# Example output from gem search --exact rails
# rails (7.1.3)
_SEARCH_GEM_PATTERN = re.compile(r'^(\S+)\s+\(([^)]+)\)')


class GemCommand(PackageManagerCommand):
    """
    A representation of `gem` commands via the `PackageManagerCommand` interface.
    """
    def __init__(self, command: list[str], executable: Optional[str] = None):
        """
        Initialize a new `GemCommand`.

        Args:
            command: A `gem` command line.
            executable:
                Optional path to the executable to run the command. Determined by the
                environment if not given.

        Raises:
            ValueError: An invalid `gem` command line was given.
            UnsupportedVersionError:
                An unsupported version of `gem` was used to initialize a GemCommand.
        """
        def get_executable() -> str:
            return executable if executable else "gem"

        def get_gem_version(executable: str) -> Version:
            try:
                gem_version_command = [executable, "--version"]
                gem_version = subprocess.run(gem_version_command, check=True, text=True, capture_output=True)
                version_str = gem_version.stdout.strip()
                return version_parse(version_str)
            except subprocess.CalledProcessError:
                raise UnsupportedVersionError(_UNSUPPORTED_GEM_VERSION)

        if not command or command[0] != "gem":
            raise ValueError("Malformed gem command")
        self._command = command

        self._executable = get_executable()
        if get_gem_version(self._executable) < MIN_GEM_VERSION:
            raise UnsupportedVersionError(_UNSUPPORTED_GEM_VERSION)

    def run(self):
        """
        Run a `gem` command.
        """
        subprocess.run(self._command)

    def would_install(self) -> list[InstallTarget]:
        """
        Determine the list of Ruby gems a `gem` command would install if it were run.

        Returns:
            A `list[InstallTarget]` representing the gems the `gem` command would
            install if it were run.

        Raises:
            ValueError: The `gem` output did not have the required format.
        """
        # Gem installs or downloads gems via `gem install` or `gem fetch` commands
        # If none are present, or if --help is present, or if install --explain is present,
        # the command is automatically safe to run
        if (not any(cmd in self._command for cmd in ["install", "fetch"]) or
            "--help" in self._command or
                ("install" in self._command and "--explain" in self._command)):
            return []

        try:
            targets = []

            if "install" in self._command:
                explain_command = self._command.copy()
                explain_command.append("--explain")

                explain_output = subprocess.run(explain_command, text=True, capture_output=True)
                _log.debug("gem install --explain output: %s", explain_output)

                in_gems_section = False
                for line in explain_output.stdout.splitlines():
                    if line.strip() == "Gems to install:":
                        in_gems_section = True
                        continue

                    if in_gems_section and (match := _INSTALL_GEM_PATTERN.match(line)):
                        name, version = match.groups()
                        _log.debug("Found gem to install: %s %s", name, version)
                        targets.append(InstallTarget(ECOSYSTEM.GEM, name, version))

            elif "fetch" in self._command:
                # For gem fetch, we need to determine the version that would be downloaded
                try:
                    fetch_idx = self._command.index("fetch")
                    if fetch_idx + 1 >= len(self._command):
                        return []

                    # Find version flag if present
                    version = None
                    version_idx = None
                    for i, arg in enumerate(self._command):
                        if arg.startswith(("--version=", "-v=")):
                            version = arg.split("=", 1)[1]
                            version_idx = i
                            break
                        elif arg in ["--version", "-v"] and i + 1 < len(self._command):
                            version = self._command[i + 1]
                            version_idx = i
                            break

                    # Process all gems after 'fetch' command and before version flag (if any)
                    gem_names = []
                    for i in range(fetch_idx + 1, len(self._command)):
                        if version_idx is not None and i >= version_idx:
                            break
                        if self._command[i].startswith("-"):
                            break
                        gem_names.append(self._command[i])

                    for gem_spec in gem_names:
                        gem_name = gem_spec
                        gem_version = version  # Use version from flag if present

                        # Check for name:version format which overrides --version
                        if ":" in gem_spec:
                            gem_name, gem_version = gem_spec.split(":", 1)

                        if gem_version:
                            targets.append(InstallTarget(ECOSYSTEM.GEM, gem_name, gem_version))
                        else:
                            # Use gem search --exact to find the latest version
                            search_command = [self._executable, "search", "--exact", gem_name]
                            search_output = subprocess.run(search_command, text=True, capture_output=True)

                            for line in search_output.stdout.splitlines():
                                if match := _SEARCH_GEM_PATTERN.match(line):
                                    name, version = match.groups()
                                    targets.append(InstallTarget(ECOSYSTEM.GEM, name, version))
                                    break

                except (ValueError, IndexError):
                    _log.debug("Could not parse gem fetch command")
                    return []

            _log.debug("Found gem targets: %s", targets)
            return targets

        except subprocess.CalledProcessError:
            # An error occurred while collecting targets
            # As we can't determine what would be installed, return empty list
            _log.info("The gem command encountered an error while collecting installation targets")
            return []
