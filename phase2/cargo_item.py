"""Cargo item model and in-memory directory for the cargo tracking system."""

from __future__ import annotations

import json
from itertools import count
from typing import Any, Dict, List, Optional, Tuple


class CargoItem:
    """Represents a single cargo item and its tracking state."""

    _id_sequence = count(1)
    _allowed_update_fields = {
        "sendernam": "sender_name",
        "sender_name": "sender_name",
        "recipnam": "recipient_name",
        "recipient_name": "recipient_name",
        "recipaddr": "recipient_address",
        "recipient_address": "recipient_address",
        "owner": "owner",
        "state": "state",
    }
    ######### CRUD #############
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
        self._deleted = False

    def get(self) -> str:
        """Return a JSON representation of the cargo item."""
        payload = {
            "id": self._tracking_id,
            "sendernam": self.sender_name,
            "recipnam": self.recipient_name,
            "recipaddr": self.recipient_address,
            "owner": self.owner,
            "state": self.state,
            "container": self._container_id,
            "deleted": self._deleted,
        }
        return json.dumps(payload, sort_keys=True)
    
    def update(self, **updates: Any) -> None:
        if not updates:
            return

        if self._deleted:
            raise RuntimeError("Cargo item has been deleted")

        changed = False
        for key, value in updates.items():
            attr = self._allowed_update_fields.get(key)
            if attr is None:
                raise AttributeError(f"Unknown field '{key}'")
            if value is None or (isinstance(value, str) and not value.strip()):
                raise ValueError(f"Invalid value for '{key}'")

            current = getattr(self, attr)
            if current != value:
                setattr(self, attr, value)
                changed = True

        if changed:
            self.updated()



    def delete(self) -> None:
        if self._deleted:
            return
        self._deleted = True
        self.state = "deleted"
        self._container = None
        self._container_id = None
        self.updated()
        self._trackers.clear()

    def trackingId(self) -> str:
        return self._tracking_id

    def getContainer(self) -> Optional[Any]:
        return self._container_id

    def setContainer(self, container: Any) -> None:
        if self._deleted:
            raise RuntimeError("Cargo item has been deleted")

        self._container = container
        if container is None:
            self._container_id = None
        elif hasattr(container, "cid"):
            self._container_id = getattr(container, "cid")
        elif hasattr(container, "trackingId") and callable(container.trackingId):
            self._container_id = container.trackingId()
        else:
            self._container_id = container

        # attempt to align the item state with the container's declared state
        if container is None:
            if self.state != "complete":
                self.state = "accepted"
        else:
            state = None
            if hasattr(container, "getState") and callable(container.getState):
                try:
                    state = container.getState()
                except Exception:
                    pass
            if isinstance(state, str) and state:
                self.state = state

        self.updated()

    def updated(self) -> None:
        for tracker in list(self._trackers):
            try:
                tracker.updated(self)
            except TypeError:
                tracker.updated()

    def complete(self) -> None:
        if self._deleted:
            raise RuntimeError("Cargo item has been deleted")

        self.state = "complete"
        self.updated()

    def track(self, tracker: Any) -> None:
        if self._deleted:
            raise RuntimeError("Cargo item has been deleted")

        if tracker is None:
            raise ValueError("tracker must not be None")
        try:
            self._trackers.add(tracker)
        except TypeError as exc:
            raise TypeError("tracker objects not hashable") from exc

    def untrack(self, tracker: Any) -> None:
        if self._deleted:
            raise RuntimeError("Cargo item has been deleted")

        self._trackers.discard(tracker)

class CargoDirectory:
    """In-memory catalog for cargo items supporting CRUD operations."""

    def __init__(self) -> None:
        self._items: Dict[str, CargoItem] = {}
        self._attachments: Dict[str, set[str]] = {}

    def create(self, **kwargs: Any) -> str:
        item = CargoItem(**kwargs)
        item_id = item.trackingId()
        if item_id in self._items:
            raise RuntimeError("Duplicate cargo item identifier generated")
        self._items[item_id] = item
        return item_id

    def list(self) -> List[Tuple[str, str]]:
        return [(item_id, item.get()) for item_id, item in self._items.items()]

    def listattached(self, user: str) -> List[Tuple[str, str]]:
        if not isinstance(user, str) or not user.strip():
            raise ValueError("user must be a non-empty string")

        result: List[Tuple[str, str]] = []
        for item_id, users in self._attachments.items():
            if user in users and item_id in self._items:
                result.append((item_id, self._items[item_id].get()))
        return result

    def get(self, item_id: str) -> CargoItem:
        if item_id not in self._items:
            raise KeyError(item_id)
        return self._items[item_id]

    def attach(self, item_id: str, user: str) -> CargoItem:
        if not isinstance(user, str) or not user.strip():
            raise ValueError("user must be a non-empty string")

        item = self._items[item_id]
        self._attachments.setdefault(item_id, set()).add(user)
        return item

    def detach(self, item_id: str, user: str) -> None:
        if not isinstance(user, str) or not user.strip():
            raise ValueError("user must be a non-empty string")

        if item_id not in self._items:
            raise KeyError(item_id)
        users = self._attachments.get(item_id)
        if not users or user not in users:
            raise KeyError(f"User '{user}' not attached to item '{item_id}'")
        users.remove(user)
        if not users:
            self._attachments.pop(item_id, None)

    def delete(self, item_id: str) -> None:
        item = self._items[item_id]
        attached = self._attachments.get(item_id)
        if attached:
            raise RuntimeError("Cannot delete an item while it is attached")
        item.delete()
        self._items.pop(item_id, None)

