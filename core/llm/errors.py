"""Errors raised by LLM providers.

The API layer translates :class:`LLMError` into a user-friendly 502 response;
technical details are logged, never shown verbatim to the user.
"""


class LLMError(Exception):
    """The language model could not produce a response."""


class LLMConfigurationError(LLMError):
    """The provider/model configuration is incomplete or invalid."""
