from __future__ import annotations

import logging
from collections import deque

from mcp.server.session import ServerSession

logger = logging.getLogger(__name__)


class SessionStore:
    """
    Global singleton object that implements the elicitation_id to ServerSession mapping.
    Before a tool call handler function returns a URL mode elicitation, it sets the map from elicitation_id to session.
    When the /oauth/callback route receives the callback request, on success, it retrieves the session object
    via elicitation_id (passed via the "state" parameter) and uses the session to make a best-effort notification
    to client on elicitation completion.
    """

    _max_session_count: int
    _mapping: dict[str, ServerSession]
    _elicitation_order: deque[str]

    def __init__(self, max_session_count: int = 100):
        self._max_session_count = max_session_count
        self._mapping = {}
        self._elicitation_order = deque(maxlen=self._max_session_count)

    def append(self, elicitation_id: str, session: ServerSession):
        # The elicitation_id to session mapping cannot be updated once set.
        # In practice, elicitation_id is a newly generated UUID for each unique elicitation request,
        # so normally we will not see the same ID being appended again.
        if elicitation_id in self._mapping:
            return

        # If we are at max capacity, pop the oldest elicitation_id and its corresponding session.
        if len(self._mapping) >= self._max_session_count:
            oldest_id = self._elicitation_order.popleft()
            self._mapping.pop(oldest_id, None)

        self._mapping[elicitation_id] = session
        self._elicitation_order.append(elicitation_id)

    def pop(self, elicitation_id: str) -> ServerSession | None:
        try:
            self._elicitation_order.remove(elicitation_id)
        except Exception as e:
            logger.error(f"Failed to remove {elicitation_id}: {e}")
            logger.exception(f"trying to remove elicitation_id {elicitation_id} that doesn't exist in the deque.")

        return self._mapping.pop(elicitation_id, None)
