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


def test_1():  # Tests tracking ID format and defaults
    item = make_item()

    assert re.fullmatch(r"CI\d{8}", item.trackingId())
    assert item.state == "accepted"
    assert item.getContainer() is None


@pytest.mark.parametrize(
    "field",
    ["sendernam", "recipnam", "recipaddr", "owner"],
)
def test_2(field):  # Tests constructor requires all fields
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


def test_3():  # Tests set container updates state and ID
    item = make_item()
    container = DummyContainer(state="waiting", cid="CONT-9")

    item.setContainer(container)

    assert item.getContainer() == "CONT-9"
    assert item.state == "waiting"


def test_4():  # Tests set container none resets state if not complete
    item = make_item()
    container = DummyContainer(state="in transit")

    item.setContainer(container)
    item.setContainer(None)

    assert item.getContainer() is None
    assert item.state == "accepted"


def test_5():  # Tests complete marks item complete
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


def test_6():  # Tests untrack stops notifications
    item = make_item()
    tracker = TrackerWithArg()

    item.track(tracker)
    item.untrack(tracker)
    item.updated()

    assert tracker.calls == []


def test_7():  # Tests track validates inputs
    item = make_item()

    with pytest.raises(ValueError):
        item.track(None)

    with pytest.raises(TypeError):
        item.track([])


def test_8():  # Tests get returns serialized snapshot
    item = make_item()

    snapshot = json.loads(item.get())

    assert snapshot["id"] == item.trackingId()
    assert snapshot["sendernam"] == "Nehir"
    assert snapshot["deleted"] is False


def test_9():  # Tests update rejects unknown fields
    item = make_item()

    with pytest.raises(AttributeError):
        item.update(foo="bar")


def test_10():  # Tests delete marks item and blocks future changes
    item = make_item()
    item.delete()

    assert item.state == "deleted"
    assert item.getContainer() is None
    with pytest.raises(RuntimeError):
        item.update(sendernam="Another")


def test_11():  # Tests directory create list attach detach delete flow
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


def test_12():  # Tests directory delete requires detach first
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
