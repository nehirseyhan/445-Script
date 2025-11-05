"""Cargo item model for the cargo delivery and tracking system."""

from __future__ import annotations

from itertools import count
from typing import Any, Optional


class CargoItem:
    """Represents a single cargo item and its tracking state."""

    _id_sequence = count(1)

    def __init__(
        self,
        sendernam: str,
        recipnam: str,
        recipaddr: str,
        owner: str,
    ) -> None:
        if not sendernam:
            raise ValueError("sendernam not provided")
        if not recipnam:
            raise ValueError("recipnam not provided")
        if not recipaddr:
            raise ValueError("recipaddr not provided")
        if not owner:
            raise ValueError("owner not provided")

        self.sender_name = sendernam
        self.recipient_name = recipnam
        self.recipient_address = recipaddr
        self.owner = owner

        self._tracking_id = f"CI{next(self._id_sequence):08d}"
        self.state = "accepted"
        self._container: Any = None
        self._container_id: Optional[Any] = None
        self._trackers: set[Any] = set()

    def trackingId(self) -> str:
        return self._tracking_id

    def getContainer(self) -> Optional[Any]:
        return self._container_id

    def setContainer(self, container: Any) -> None:
        self._container = container
        self._container_id = self._resolve_container_id(container)

        # attempt to align the item state with the container's declared state
        if container is None:
            if self.state != "complete":
                self.state = "accepted"
        else:
            state = self._state_from_container(container)
            if state:
                self.state = state

        self.updated()

    def updated(self) -> None:
        for tracker in list(self._trackers):
            self._notify_tracker(tracker)

    def complete(self) -> None:
        self.state = "complete"
        self.updated()

    def track(self, tracker: Any) -> None:
        if tracker is None:
            raise ValueError("tracker must not be None")
        try:
            self._trackers.add(tracker)
        except TypeError as exc:
            raise TypeError("tracker objects not hashable") from exc

    def untrack(self, tracker: Any) -> None:
        self._trackers.discard(tracker)

    def _notify_tracker(self, tracker: Any) -> None:
        try:
            tracker.updated(self)
        except TypeError:
            tracker.updated()

    @staticmethod
    def _resolve_container_id(container: Any) -> Optional[Any]:
        if container is None:
            return None

        if hasattr(container, "cid"):
            return getattr(container, "cid")
        if hasattr(container, "getid") and callable(container.getid):
            return container.getid()
        if hasattr(container, "trackingId") and callable(container.trackingId):
            return container.trackingId()

        return container

    @staticmethod
    def _state_from_container(container: Any) -> Optional[str]:
        if hasattr(container, "getState") and callable(container.getState):
            try:
                state = container.getState()
            except Exception:
                return None
            if isinstance(state, str) and state:
                return state
        return None
