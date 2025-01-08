"""
Defines a test verifier that always returns a CRITICAL finding.
This is useful for testing the verification pipeline.
"""
import os
from scfw.target import InstallTarget
from scfw.verifier import FindingSeverity, InstallTargetVerifier


class TestVerifier(InstallTargetVerifier):
    """
    An `InstallTargetVerifier` that returns findings based on environment variables.
    Used for testing purposes.
    """
    def name(self) -> str:
        """
        Return the verifier name string.

        Returns:
            The class' constant name string: "TestVerifier"
        """
        return "TestVerifier"

    def verify(self, target: InstallTarget) -> list[tuple[FindingSeverity, str]]:
        """
        Always returns a CRITICAL finding for any target.

        Args:
            target: The installation target to verify.

        Returns:
            A list containing a single CRITICAL finding.
        """
        severity = os.getenv("SCFW_SEVERITY", '')

        if severity == 'CRITICAL' or severity == 'WARNING':
            return [
                (
                    FindingSeverity.CRITICAL if severity == 'CRITICAL' else FindingSeverity.WARNING,
                    f"Test verifier {severity} finding for package {target}"
                )
            ]
        # Default
        return []


def load_verifier() -> InstallTargetVerifier:
    """
    Export `TestVerifier` for discovery by the firewall.

    Returns:
        A `TestVerifier` for use in testing the supply chain firewall.
    """
    return TestVerifier()
