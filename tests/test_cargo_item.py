import json
import re

import pytest

from cargo_item import CargoDirectory, CargoItem


def make_item(**overrides):
    params = {
        "sendernam": "Nehir",
        "recipnam": "Aybeniz",
        "recipaddr": "Ankara",
        "owner": "Carrier",
    }
    params.update(overrides)
    return CargoItem(**params)


def test_tracking_id_format_and_defaults():
    item = make_item()

    assert re.fullmatch(r"CI\d{8}", item.trackingId())
    assert item.state == "accepted"
    assert item.getContainer() is None


@pytest.mark.parametrize(
    "field",
    ["sendernam", "recipnam", "recipaddr", "owner"],
)
def test_constructor_requires_all_fields(field):
    kwargs = {
        "sendernam": "Nehir",
        "recipnam": "Aybeniz",
        "recipaddr": "Ankara",
        "owner": "Carrier",
    }
    kwargs[field] = ""

    with pytest.raises(ValueError):
        CargoItem(**kwargs)


class DummyContainer:
    def __init__(self, state="waiting", cid="CONT-1"):
        self.cid = cid
        self._state = state

    def getState(self):
        return self._state


def test_set_container_updates_state_and_id():
    item = make_item()
    container = DummyContainer(state="waiting", cid="CONT-9")

    item.setContainer(container)

    assert item.getContainer() == "CONT-9"
    assert item.state == "waiting"


def test_set_container_none_resets_state_if_not_complete():
    item = make_item()
    container = DummyContainer(state="in transit")

    item.setContainer(container)
    item.setContainer(None)

    assert item.getContainer() is None
    assert item.state == "accepted"


def test_complete_marks_item_complete():
    item = make_item()

    item.complete()

    assert item.state == "complete"


class TrackerWithArg:
    def __init__(self):
        self.calls = []

    def updated(self, item):
        self.calls.append(item)


class TrackerWithoutArg:
    def __init__(self):
        self.count = 0

    def updated(self):
        self.count += 1


def test_updated_notifies_all_trackers():
    item = make_item()
    tracker_with_arg = TrackerWithArg()
    tracker_without_arg = TrackerWithoutArg()

    item.track(tracker_with_arg)
    item.track(tracker_without_arg)

    item.updated()

    assert tracker_with_arg.calls == [item]
    assert tracker_without_arg.count == 1


def test_set_container_triggers_update_notification():
    item = make_item()
    tracker = TrackerWithArg()
    item.track(tracker)

    item.setContainer(DummyContainer())

    assert tracker.calls[-1] is item


def test_untrack_stops_notifications():
    item = make_item()
    tracker = TrackerWithArg()

    item.track(tracker)
    item.untrack(tracker)
    item.updated()

    assert tracker.calls == []


def test_track_validates_inputs():
    item = make_item()

    with pytest.raises(ValueError):
        item.track(None)

    with pytest.raises(TypeError):
        item.track([])


def test_get_returns_serialized_snapshot():
    item = make_item()

    snapshot = json.loads(item.get())

    assert snapshot["id"] == item.trackingId()
    assert snapshot["sendernam"] == "Nehir"
    assert snapshot["deleted"] is False


def test_update_changes_fields_and_notifies_trackers():
    item = make_item()
    tracker = TrackerWithArg()
    item.track(tracker)

    item.update(sendernam="Updated Sender")

    assert item.sender_name == "Updated Sender"
    assert tracker.calls[-1] is item


def test_update_rejects_unknown_fields():
    item = make_item()

    with pytest.raises(AttributeError):
        item.update(foo="bar")


def test_delete_marks_item_and_blocks_future_changes():
    item = make_item()
    item.delete()

    assert item.state == "deleted"
    assert item.getContainer() is None
    with pytest.raises(RuntimeError):
        item.update(sendernam="Another")


def test_directory_create_list_attach_detach_delete_flow():
    directory = CargoDirectory()
    item_id = directory.create(
        sendernam="S",
        recipnam="R",
        recipaddr="Addr",
        owner="Owner",
    )

    listed = dict(directory.list())
    assert item_id in listed

    item = directory.attach(item_id, "user1")
    assert isinstance(item, CargoItem)

    attached = dict(directory.listattached("user1"))
    assert item_id in attached

    directory.detach(item_id, "user1")
    assert directory.listattached("user1") == []

    directory.delete(item_id)
    assert directory.list() == []


def test_directory_delete_requires_detach_first():
    directory = CargoDirectory()
    item_id = directory.create(
        sendernam="S",
        recipnam="R",
        recipaddr="Addr",
        owner="Owner",
    )
    directory.attach(item_id, "user1")

    with pytest.raises(RuntimeError):
        directory.delete(item_id)

    directory.detach(item_id, "user1")
    directory.delete(item_id)

    assert directory.list() == []
