"""Errors raised by LLM providers.

The API layer translates :class:`LLMError` into a user-friendly 502 response;
technical details are logged, never shown verbatim to the user.
"""


class LLMError(Exception):
    """The language model could not produce a response."""


class LLMConfigurationError(LLMError):
    """The provider/model configuration is incomplete or invalid."""


class LLMRateLimitError(LLMError):
    """The provider temporarily rejected a request because of rate limits."""

    def __init__(
        self,
        message: str = "The language model is temporarily rate limited.",
        *,
        provider: str = "unknown",
        retry_after: str | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.retry_after = retry_after
