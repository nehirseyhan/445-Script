import json
import pytest

from tracker import Tracker
from container import Container
from cargo_item import CargoItem

class MockCargoItem:
   
    def __init__(self, item_id="MOCK_CI001"):
        self.id = item_id
        self.state = "accepted"
        self._container = None
        self.track_calls = []
        self.untrack_calls = []

    def getid(self):
        return self.id
    
    def getContainer(self):
        return None

    def track(self, tracker):
        self.track_calls.append(tracker)

    def untrack(self, tracker):
        self.untrack_calls.append(tracker)

    def updated(self):
        pass # Not needed for this mock

class MockContainer:
   
    def __init__(self, cid="MOCK_CONT1", loc=(0.0, 0.0)):
        self.cid = cid
        self.loc = loc
        self.track_calls = []
        self.untrack_calls = []

    def getid(self):
        return self.cid

    def track(self, tracker):
        self.track_calls.append(tracker)

    def untrack(self, tracker):
        self.untrack_calls.append(tracker)


# --- Pytest Fixtures ---

@pytest.fixture
def sample_tracker():
    """Returns a default, empty tracker."""
    return Tracker(tid="TRK1", description="My Tracker", owner="user1")


@pytest.fixture
def sample_container():
    """Returns a real, default container."""
    return Container(cid="CONT1", description="Main Hub", type="Hub", loc=(20.0, 10.0))


@pytest.fixture
def sample_item():
    """Returns a real, default cargo item."""
    return CargoItem(
        sendernam="Test Sender",
        recipnam="Test Recipient",
        recipaddr="Test Address",
        owner="Test Owner",
    )


# --- Tracker Tests ---

class TestTracker:
    def test_1(self, sample_tracker):
        # Test constructor and get method
        trk = sample_tracker
        
        assert trk.tid == "TRK1"
        assert trk.owner == "user1"
        
        data = json.loads(trk.get())
        assert data["tid"] == "TRK1"
        assert data["owner"] == "user1"
        assert data["tracked_items"] == []
        assert data["tracked_containers"] == []
        assert data["view_rect"] is None
        assert data["deleted"] is False

    def test_2(self, sample_tracker):
        # Test update method
        trk = sample_tracker

        trk.update(description="New Desc", owner="New Owner")

        assert trk.description == "New Desc"
        assert trk.owner == "New Owner"
        
        with pytest.raises(AttributeError):
            trk.update(tid="TRK2")
        with pytest.raises(ValueError):
            trk.update(description="")

    def test_3(self, sample_tracker):
        # Test add item
        trk = sample_tracker
        item = MockCargoItem()
        
        trk.addItem([item])
        
        assert len(item.track_calls) == 1
        assert item.track_calls[0] is trk
        assert item in trk._items

    def test_4(self, sample_tracker):
        # Test add container
        trk = sample_tracker
        cont = MockContainer()
        
        trk.addContainer([cont])
        
        assert len(cont.track_calls) == 1
        assert cont.track_calls[0] is trk
        assert cont in trk._containers

    def test_5(self, sample_tracker, capsys):
        # Test updated captures print
        trk = sample_tracker
        
        trk.updated(MockContainer(cid="TEST_CONT"))
        
        captured = capsys.readouterr()
        assert "Tracker TRK1: Received update from TEST_CONT" in captured.out

    def test_6(self, sample_tracker, sample_item, sample_container):
        # Test get stat list
        trk = sample_tracker
        item = sample_item
        cont = sample_container
        
        item.setContainer(cont)
        trk.addItem([item])
        
        stats = trk.getStatlist()
        
        assert len(stats) == 1
        assert stats[0]["id"] == item.trackingId()
        assert stats[0]["state"] == "waiting"
        assert stats[0]["location"] == (20.0, 10.0)
        assert stats[0]["container_id"] == cont.cid

    def test_7(self, sample_tracker, sample_item, sample_container):
        # Test set view filters stat list
        trk = sample_tracker
        item = sample_item
        cont = sample_container
        item.setContainer(cont)
        trk.addItem([item])
        
        trk.setView(top=30, left=0, bottom=0, right=30)
        stats_inside = trk.getStatlist()
        
        assert len(stats_inside) == 1
        
        trk.setView(top=5, left=0, bottom=0, right=5)
        stats_outside = trk.getStatlist()

        assert len(stats_outside) == 0

    def test_8(self, sample_tracker, sample_item, sample_container, capsys):
        # Test set view filters updates
        trk = sample_tracker
        item = sample_item
        cont = sample_container
        item.setContainer(cont)
        trk.addItem([item])
        trk.addContainer([cont])
        
        trk.setView(top=5, left=0, bottom=0, right=5)
        item.updated()
        cont.updated()
        
        captured = capsys.readouterr()
        assert f"Ignoring update from {item.trackingId()}" in captured.out
        assert f"Ignoring update from {cont.cid}" in captured.out
        
        trk.setView(top=30, left=0, bottom=0, right=30)
        item.updated()
        
        captured = capsys.readouterr()
        assert f"Received update from {item.trackingId()}" in captured.out

