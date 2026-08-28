from typing import Protocol

from app.models.domain import Opportunity


class ConnectorError(Exception):
    """Public-safe base error for external job source failures."""


class ConnectorTimeoutError(ConnectorError):
    """The upstream source did not respond within the configured timeout."""


class ConnectorPayloadError(ConnectorError):
    """The upstream source returned a payload that cannot be normalized safely."""


class JobConnector(Protocol):
    async def fetch(self) -> list[Opportunity]: ...
