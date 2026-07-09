import os
import re
import logging
from typing import Set

logger = logging.getLogger(__name__)

class SecretScrubber:
    """
    Cleans logs, stdout, and PR bodies of sensitive credentials,
    secrets, and authentication tokens.
    """
    def __init__(self):
        self.sensitive_values: Set[str] = set()
        self._load_secrets_from_env()

        # Regular expressions for common secret formats
        self.regex_patterns = [
            # GitHub Tokens (ghp_ or ghs_ prefixes)
            re.compile(r'gh[ps]_[a-zA-Z0-9]{36,255}'),
            # OpenAI API Keys
            re.compile(r'sk-[a-zA-Z0-9]{48}'),
            re.compile(r'sk-proj-[a-zA-Z0-9\-_]{20,}'),
            # Anthropic API Keys
            re.compile(r'sk-ant-sid01-[a-zA-Z0-9\-_]{40,255}'),
            # AWS Access Key ID & Secret Access Key
            re.compile(r'(?<![A-Z0-9])[A-Z0-9]{20}(?![A-Z0-9])'), # AWS Access Key ID candidate
            re.compile(r'(?<![A-Za-z0-9/+=])[A-Za-z0-9/+=]{40}(?![A-Za-z0-9/+=])') # Secret key candidate
        ]

    def _load_secrets_from_env(self):
        """Dynamically collects secret values from environment variables."""
        secret_indicators = ["KEY", "SECRET", "TOKEN", "PASSWORD", "PASS", "AUTH"]
        for env_name, env_val in os.environ.items():
            if any(ind in env_name.upper() for ind in secret_indicators):
                if len(env_val) > 4:  # Only redact keys that have substantial length
                    self.sensitive_values.add(env_val)

    def scrub(self, text: str) -> str:
        """
        Scrubs all sensitive content from a text string and replaces
        it with a placeholder.
        """
        if not text:
            return ""

        scrubbed = text

        # 1. Scrub matched environment variables
        for secret in sorted(self.sensitive_values, key=len, reverse=True):
            if secret in scrubbed:
                scrubbed = scrubbed.replace(secret, "[REDACTED_SECRET]")

        # 2. Scrub via regular expressions
        for pattern in self.regex_patterns:
            scrubbed = pattern.sub("[REDACTED_SECRET]", scrubbed)

        return scrubbed
