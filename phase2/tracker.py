"""Tracker model for the cargo tracking system."""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from cargo_item import CargoItem
from container import Container


class Tracker:
    """
    Tracks a set of CargoItems and Containers, notifying of state changes.
    """

    _allowed_update_fields = {
        "description": "description",
        "owner": "owner",
    }
 ######### CRUD #############
    def __init__(
        self,
        tid: str,
        description: str,
        owner: str,
        on_update: Optional[Callable[["Tracker", Optional[Any], str], None]] = None,
    ) -> None:

        if not tid:
            raise ValueError("tid not provided")
        if not description:
            raise ValueError("description not provided")
        if not owner:
            raise ValueError("owner not provided")

        self.tid = tid
        self.description = description
        self.owner = owner

        self._items: Set[CargoItem] = set()
        self._containers: Set[Container] = set()
        self._view_rect: Optional[Tuple[float, float, float, float]] = None
        self._deleted = False
        self._on_update = on_update

    def get(self) -> str:
        """Return a JSON representation of the tracker."""
        payload = {
            "tid": self.tid,
            "description": self.description,
            "owner": self.owner,
            "tracked_items": [item.trackingId() for item in self._items],
            "tracked_containers": [cont.cid for cont in self._containers],
            "view_rect": self._view_rect,
            "deleted": self._deleted,
        }
        return json.dumps(payload, sort_keys=True)

    def update(self, **updates: Any) -> None:
        """Update mutable fields of the tracker."""
        if not updates:
            return
        if self._deleted:
            raise RuntimeError(f"Tracker '{self.tid}' has been deleted")

        for key, value in updates.items():
            attr = self._allowed_update_fields.get(key)
            if attr is None:
                raise AttributeError(f"Unknown field '{key}'")
            if value is None or (isinstance(value, str) and not value.strip()):
                raise ValueError(f"Invalid value for '{key}'")

            setattr(self, attr, value)

    def delete(self) -> None:
        """Mark the tracker as deleted and stop tracking all objects."""
        if self._deleted:
            return
        self._deleted = True

        # Untrack all items
        for item in list(self._items):
            self._items.remove(item)
            item.untrack(self)
        # Untrack all containers
        for cont in list(self._containers):
            self._containers.remove(cont)
            cont.untrack(self)

    def addItem(self, itemlist: List[CargoItem]) -> None:
        """Adds a list of cargo items to track."""
        if self._deleted:
            raise RuntimeError(f"Tracker '{self.tid}' has been deleted")

        for item in itemlist:
            if item not in self._items:
                self._items.add(item)
                item.track(self)

    def addContainer(self, contlist: List[Container]) -> None:
        """Adds a list of containers to track."""
        if self._deleted:
            raise RuntimeError(f"Tracker '{self.tid}' has been deleted")

        for cont in contlist:
            if cont not in self._containers:
                self._containers.add(cont)
                cont.track(self)

    def updated(self, updated_object: Optional[Any] = None) -> None:
        """
        Callback method called by tracked objects to inform of changes.
        """
        if self._deleted:
            raise RuntimeError(f"Tracker '{self.tid}' has been deleted")

        if not updated_object:
            print(f"Tracker {self.tid}: Received a generic update.")
            return

        obj_id = "unknown"
        if hasattr(updated_object, "trackingId"):
            obj_id = updated_object.trackingId()
        elif hasattr(updated_object, "cid"):
            obj_id = updated_object.cid
        elif hasattr(updated_object, "tid"):
            obj_id = updated_object.tid

        # If a view rectangle is set, filter updates based on location
        if self._view_rect:
            loc = self._resolve_location(updated_object)
            if loc is not None and not self._loc_in_view(loc):
                # Ignore updates from objects outside the view
                print(f"Tracker {self.tid}: Ignoring update from {obj_id} (outside view).")
                return

        # Per project spec, phase 1 just prints to terminal
        print(f"Tracker {self.tid}: Received update from {obj_id}.")
        self._emit_update(updated_object, obj_id)

    def getStatlist(self) -> List[Dict[str, Any]]:
        """
        Returns a list of states for the tracked items, including locations.
        """
        if self._deleted:
            raise RuntimeError(f"Tracker '{self.tid}' has been deleted")

        results: List[Dict[str, Any]] = []

        for item in self._items:
            loc = None
            if hasattr(item, "_container") and item._container:
                container_obj = item._container
                if hasattr(container_obj, "loc"):
                    loc = container_obj.loc

            # Apply view filter if it exists
            if self._view_rect:
                if loc is None:
                    # Item has no location, skip if view is set
                    continue
                if not self._loc_in_view(loc):
                    continue  # Skip item, outside view

            status_record = {
                "id": item.trackingId(),
                "state": item.state,
                "location": loc,
                "container_id": item.getContainer(),
            }
            results.append(status_record)

        return results

    def setView(self, top: float, left: float, bottom: float, right: float) -> None:
        """
        Restricts reports to the geographical rectangle.
        top: Max latitude
        left: Min longitude
        bottom: Min latitude
        right: Max longitude
        """
        if self._deleted:
            raise RuntimeError(f"Tracker '{self.tid}' has been deleted")

        try:
            self._view_rect = (
                float(top),
                float(left),
                float(bottom),
                float(right),
            )
        except (ValueError, TypeError) as exc:
            raise ValueError("Invalid view coordinates") from exc

    def inView(self, obj: Any) -> bool:
        """Return True if the object's location falls within the current view."""
        if self._view_rect is None:
            return True
        loc = self._resolve_location(obj)
        if loc is None:
            return False
        return self._loc_in_view(loc)

    def _resolve_location(self, obj: Optional[Any]) -> Optional[Tuple[float, float]]:
        if obj is None:
            return None
        if isinstance(obj, Container):
            return getattr(obj, "loc", None)
        if isinstance(obj, CargoItem):
            container_obj = getattr(obj, "_container", None)
            if container_obj is not None and hasattr(container_obj, "loc"):
                return container_obj.loc
        return None

    def _loc_in_view(self, loc: Tuple[float, float]) -> bool:
        if self._view_rect is None:
            return True
        top, left, bottom, right = self._view_rect
        lon, lat = loc
        return left <= lon <= right and bottom <= lat <= top

    def _emit_update(self, updated_object: Optional[Any], obj_id: str) -> None:
        if not self._on_update:
            return
        try:
            self._on_update(self, updated_object, obj_id)
        except Exception as exc:
            print(f"Tracker {self.tid}: update callback failed: {exc}")

