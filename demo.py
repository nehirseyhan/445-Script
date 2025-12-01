"""Tiny cargo-tracking demo so you can see the model working."""

import json

from cargo_item import CargoDirectory
from container import Container
from tracker import Tracker


def run_demo():
    print("\n=== Cargo Tracking Demo ===\n")

    directory = CargoDirectory()
    tracker = Tracker(tid="TRK-DEMO", description="Operations Dashboard", owner="demo@ops")
    truck = Container(cid="CONT-DEMO", description="Linehaul Truck", type="Truck", loc=(32.86, 39.93))

    item_id = directory.create(
        sendernam="Nehir",
        recipnam="Aybeniz",
        recipaddr="Ankara",
        owner="Carrier",
    )
    item = directory.get(item_id)

    tracker.addItem([item])
    tracker.addContainer([truck])

    print(f"Created item {item_id} and registered tracker/truck.")

    truck.load([item])
    print("Loaded cargo item into truck. Tracker output:")
    item.updated()

    truck.setlocation(33.10, 40.02)
    print("Truck moved toward the hub. Latest tracker snapshot:")
    for stat in tracker.getStatlist():
        print(json.dumps(stat, indent=2))

    truck.unload([item])
    item.complete()
    print("Cargo delivered and marked complete. Final tracker snapshot:")
    for stat in tracker.getStatlist():
        print(json.dumps(stat, indent=2))


if __name__ == "__main__":
    run_demo()
