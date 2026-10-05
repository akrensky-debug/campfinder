"""
Errors the camp services raise. They know nothing about HTTP: the API turns NotFound into
a 404 (see main.py), and the agent and MCP tools turn it into a message the model can act on.
"""


class ServiceError(Exception):
    """Something the caller asked for can't be done. The message is safe to show."""

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


class NotFound(ServiceError):
    """A camp or session that doesn't exist, or that was taken off the site."""
