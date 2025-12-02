"""Container model for the cargo tracking system."""

from __future__ import annotations

import json
from typing import Any, List, Optional, Set, Tuple

from cargo_item import CargoItem

# Define container types that are stationary
STATIONARY_TYPES = {"FrontOffice", "Hub"}


class Container:
    """Represents a container (stationary or mobile) for cargo items."""

    _allowed_update_fields = {
        "description": "description",
        "type": "type",
    }
 ######### CRUD #############
    def __init__(
        self,
        cid: str,
        description: str,
        type: str,
        loc: Tuple[float, float],
    ) -> None:
        if not cid:
            raise ValueError("cid not provided")
        if not description:
            raise ValueError("description not provided")
        if not type:
            raise ValueError("type not provided")
        if not loc or not isinstance(loc, tuple) or len(loc) != 2:
            raise ValueError("loc must be a (long, latt) tuple")

        self.cid = cid
        self.description = description
        self.type = type
        self.loc = loc

        self._items: Set[CargoItem] = set()
        self._trackers: Set[Any] = set()
        self._deleted = False

    def get(self) -> str:
        """Return a JSON representation of the container."""
        payload = {
            "cid": self.cid,
            "description": self.description,
            "type": self.type,
            "loc": self.loc,
            "items": [item.getid() for item in self._items],
            "deleted": self._deleted,
        }
        return json.dumps(payload, sort_keys=True)

    def update(self, **updates: Any) -> None:
        """Update mutable fields of the container."""
        if not updates:
            return
        if self._deleted:
            raise RuntimeError(f"Container '{self.cid}' has been deleted")

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
        """Mark the container as deleted, unload items, and notify trackers."""
        if self._deleted:
            return
        self._deleted = True

        # Unload all items
        self.unload(list(self._items))

        # Notify trackers of the deletion
        self.updated()
        self._trackers.clear()

    def setlocation(self, long: float, latt: float) -> None:
        """Sets the new location of the container and notifies trackers/items."""
        if self._deleted:
            raise RuntimeError(f"Container '{self.cid}' has been deleted")

        try:
            # Basic validation
            new_loc = (float(long), float(latt))
        except (ValueError, TypeError) as exc:
            raise ValueError("Invalid location coordinates") from exc

        if self.loc != new_loc:
            self.loc = new_loc
            self.updated()

    def getState(self) -> str:
        """
        Cargo items call this to get their state based on the container.
        Returns 'waiting' for stationary containers, 'in transit' otherwise.
        """
        if self._deleted:
            raise RuntimeError(f"Container '{self.cid}' has been deleted")

        if self.type in STATIONARY_TYPES:
            return "waiting"
        return "in transit"

    def move(self, itemlist: List[CargoItem], newcontainer: Container) -> None:
        """
        Moves items from this container to a new container.
        """
        if self._deleted:
            raise RuntimeError(f"Container '{self.cid}' has been deleted")

        if newcontainer._deleted:
            raise RuntimeError(f"Container '{newcontainer.cid}' has been deleted")

        for item in itemlist:
            if item in self._items:
                self._items.remove(item)
                newcontainer._items.add(item)
                # This call triggers item.updated()
                item.setContainer(newcontainer)

    def load(self, itemlist: List[CargoItem]) -> None:
        """Loads a list of items into this container."""
        if self._deleted:
            raise RuntimeError(f"Container '{self.cid}' has been deleted")

        for item in itemlist:
            if item not in self._items:
                # Add to this container
                self._items.add(item)
                # Set item's container, which updates item state
                # and triggers item.updated()
                item.setContainer(self)

    def unload(self, itemlist: List[CargoItem]) -> None:
        """Unloads a list of items from this container."""
        if self._deleted:
            raise RuntimeError(f"Container '{self.cid}' has been deleted")

        for item in itemlist:
            if item in self._items:
                self._items.remove(item)
                # Set item's container to None, which updates item state
                # and triggers item.updated()
                item.setContainer(None)

    def track(self, tracker: Any) -> None:
        """Adds a tracker object to be notified of updates."""
        if self._deleted:
            raise RuntimeError(f"Container '{self.cid}' has been deleted")

        if tracker is None:
            raise ValueError("tracker must not be None")
        try:
            self._trackers.add(tracker)
        except TypeError as exc:
            raise TypeError("tracker objects not hashable") from exc

    def untrack(self, tracker: Any) -> None:
        """Removes a tracker object from the notification list."""
        if self._deleted:
            raise RuntimeError(f"Container '{self.cid}' has been deleted")

        self._trackers.discard(tracker)

    def updated(self) -> None:
        """
Notify all trackers and contained items of an update."""
        # Notify trackers attached to this container
        for tracker in list(self._trackers):
            try:
                # Try calling with self as argument
                tracker.updated(self)
            except TypeError:
                try:
                    # Fallback to calling with no argument
                    tracker.updated()
                except Exception:
                    # Ignore tracker errors
                    pass

        # Notify items within this container (e.g., location changed)
        # This will in turn notify trackers of those items.
        if not self._deleted:
            for item in list(self._items):
                item.updated()

