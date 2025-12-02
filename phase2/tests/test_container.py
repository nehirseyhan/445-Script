import json
import pytest

from container import Container
from cargo_item import CargoItem 

class MockCargoItem:
    """A mock CargoItem to track calls from Container."""
    def __init__(self, item_id="MOCK_CI001"):
        self.id = item_id
        self.state = "accepted"
        self._container = None
        self.setContainer_calls = []
        self.updated_calls = 0

    def getContainer(self):
        return self._container.getid() if self._container else None

    def getid(self):
        return self.id

    def setContainer(self, container):
        self._container = container
        self.setContainer_calls.append(container)

    def updated(self):
        self.updated_calls += 1


class MockTracker:
    """A mock Tracker to track calls from Container/Item."""
    def __init__(self):
        self.updated_calls = []

    def updated(self, obj=None):
        self.updated_calls.append(obj)


# --- Pytest Fixtures ---

@pytest.fixture
def sample_container():
    """Returns a default, empty container."""
    return Container(cid="CONT1", description="Main Hub", type="Hub", loc=(10.0, 20.0))


# --- Container Tests ---

class TestContainer:
    def test_1(self, sample_container):
        # Test constructor and get method
        cont = sample_container
        
        assert cont.getState() == "waiting"  # Hub is stationary
        
        data = json.loads(cont.get())
        assert data["cid"] == "CONT1"
        assert data["description"] == "Main Hub"
        assert data["type"] == "Hub"
        assert data["loc"] == [10.0, 20.0]
        assert data["items"] == []
        assert data["deleted"] is False

    def test_2(self):
        # Test constructor validation
        with pytest.raises(ValueError, match="cid not provided"):
            Container(cid="", description="Desc", type="Type", loc=(0, 0))
        with pytest.raises(ValueError, match="loc must be"):
            Container(cid="C1", description="Desc", type="Type", loc=None)
        with pytest.raises(ValueError, match="loc must be"):
            Container(cid="C1", description="Desc", type="Type", loc=(1,))

    def test_3(self):
        # Test get state logic
        stationary = Container("C1", "Office", "FrontOffice", (0, 0))
        mobile = Container("C2", "Truck", "Truck", (0, 0))
        
        assert stationary.getState() == "waiting"
        assert mobile.getState() == "in transit"

    def test_4(self, sample_container):
        # Test set location
        cont = sample_container
        tracker = MockTracker()
        cont.track(tracker)
        
        cont.setlocation(30.5, 40.5)
        
        assert cont.loc == (30.5, 40.5)
        assert len(tracker.updated_calls) == 1
        assert tracker.updated_calls[0] is cont

    def test_5(self, sample_container):
        # Test load item
        cont = sample_container
        item = MockCargoItem()
        
        cont.load([item])
        
        assert len(item.setContainer_calls) == 1
        assert item.setContainer_calls[0] is cont
        data = json.loads(cont.get())
        assert data["items"] == ["MOCK_CI001"]

    def test_6(self, sample_container):
        # Test unload item
        cont = sample_container
        item = MockCargoItem()
        cont.load([item])
        
        cont.unload([item])
        
        assert len(item.setContainer_calls) == 2
        assert item.setContainer_calls[1] is None
        data = json.loads(cont.get())
        assert data["items"] == []

    def test_7(self, sample_container):
        # Test move item
        cont1 = sample_container
        cont2 = Container("CONT2", "Truck", "Truck", (0, 0))
        item = MockCargoItem()
        cont1.load([item])
        
        cont1.move([item], cont2)
        
        assert len(item.setContainer_calls) == 2
        assert item.setContainer_calls[1] is cont2
        assert json.loads(cont1.get())["items"] == []
        assert json.loads(cont2.get())["items"] == [item.id]

    def test_8(self, sample_container):
        # Test updated notifies items
        cont = sample_container
        item = MockCargoItem()
        cont.load([item])
        
        cont.setlocation(1, 1)
        
        assert item.updated_calls == 1