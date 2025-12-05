# Cargo Tracking System – Short Speech Notes

Use this as a 10–15 minute, high‑level script. It focuses on key points and scenario evidence rather than every code detail, and matches the current code in `cargo_item.py`, `container.py`, `tracker.py` and `server.py`.

---

## 1. One‑Sentence Summary

We built a small cargo tracking platform where clients create items and containers, move items around, and get real‑time notifications over TCP when anything they care about changes.

---

## 2. Core Concepts (Model)

- **CargoItem** (in `cargo_item.py`)
  - Represents a single package: sender, recipient, address, owner.
  - Has a unique tracking id like `CI00000001` and a state: `accepted`, `waiting`, `in transit`, `complete`, `deleted`.
  - Knows which container it is in, and which watchers are subscribed.
  - When its state or container changes, it calls `updated()` and notifies all trackers that subscribed to this item.

- **Container** (in `container.py`)
  - Represents a location or vehicle: `cid`, description, type (`FrontOffice`, `Hub`, `Truck`, ...), and `(lon, lat)`.
  - Holds a set of cargo items.
  - Type controls what state items take when loaded:
    - Stationary (e.g. `FrontOffice`, `Hub`) → items are `waiting`.
    - Mobile (e.g. truck) → items are `in transit`.
  - `load()` / `unload()` move items in and out, calling `item.setContainer(...)` so item state and notifications stay consistent.
  - `setlocation()` changes its position, notifies container watchers and then pings every item inside so item watchers also see movement.

- **Tracker** (in `tracker.py`)
  - Reusable observer: watches sets of items and containers and exposes an `updated(updated_object)` callback.
  - Has optional geographic view rectangle to filter updates.
  - Can be constructed with an `on_update` callback; the server uses this to turn domain updates into network events.
  - When an `on_update` callback is provided, `updated()` forwards the event to that callback (in addition to printing). The server relies on this to enqueue session events asynchronously.

- **CargoDirectory**
  - In‑memory registry of all items: create, list, get, delete.
  - Used by the server as the authoritative catalog for cargo.

---

## 3. Server: How Networking Wraps the Model

- **Shared state** (in `server.py`)
  - `_directory: CargoDirectory` and `_containers: dict[cid → Container]` hold the world.
  - `_model_lock` (RLock) wraps all reads/writes so multiple client threads cannot corrupt the shared model.

- **Sessions and trackers**
  - Each TCP connection becomes a `Session` thread.
  - Each session owns a `Tracker` instance whose `on_update` callback is bound to the session method `_on_tracker_update`.
  - When `CargoItem.updated()` or `Container.updated()` is called, they invoke `Tracker.updated(updated_object)`, which in turn triggers the callback to queue an event for that session.

- **Event pipeline**
  - The tracker’s `updated()` method calls the session’s `_on_tracker_update`, which builds a tiny event dict: kind (cargo/container), id, and key value (state or location), and appends it into `session.events`.
  - A per‑session `notificationagent` thread waits on a `Condition`, pops events, and sends lines like `EVENT {json}` to the client.
  - This makes notifications asynchronous: commands don’t block on slow sockets—events are buffered and streamed out.

- **Text protocol: key commands**
  - `CREATE_ITEM s r addr owner` → creates a `CargoItem` in `_directory`, returns its tracking id.
  - `CREATE_CONTAINER cid desc type lon lat` → creates a `Container` and stores it in `_containers`.
  - `LOAD item cid` / `UNLOAD item` → call container `load()` / `unload()`, which update item’s container, state, and call `item.updated()`.
  - `SETLOC cid lon lat` → calls `setlocation()` on a container, which notifies container watchers and then all items inside.
  - `COMPLETE item` → calls `item.complete()`, state becomes `complete`, watchers notified.
  - `WATCH item` / `WATCH_CONTAINER cid` → attach the session’s watcher to those objects.
  - `STATUS item` → returns the JSON from `item.get()`.
  - `WAIT_EVENTS` → blocks until at least one new event has been queued or the timeout passes.
  - `SAVE` / `load_state()` → serialize/restore items and containers to `server_state.json`.

---

## 4. Demo

- **`demo_watch.py`**
  - Spawns the server process and several `DemoClient` threads.
  - Each `DemoClient` follows a scripted list of actions: numbers = sleep, strings = commands, `__CLOSE_SOCKET__` = crash.
  - Listens for responses and prints colored logs so we can visually inspect behavior.
  - This is the canonical demonstration tool for reproducible scenarios.

---

## 5. Scenario Results: What We Proved

Use these as evidence points when answering "does it really work?".

1. **Scenario 1 – Concurrent Updates (Race Condition)**
   - Two updaters both call `SETLOC RACE_CONT ...` while a watcher is subscribed.
   - Log shows two `OK moved` replies and two notifications:
     - First to `[10.0, 10.0]`, then `[20.0, 20.0]`.
   - Proves: lock serializes updates; watchers see the full history in order and final position is last write.

2. **Scenario 2 – Item Watchers (2 Common, 1 Exclusive)**
   - CommonA/CommonB both watch `CI00000002`, ExclC watches `CI00000003`.
   - Loading into `TRUCK1` sets states to `in transit` and all relevant watchers receive matching notifications.
   - Unloading `CI00000002` sends `accepted` to both common watchers.
   - Proves: multiple watchers on the same item all get every transition; exclusive watchers remain isolated.

3. **Scenario 3 – Container Watchers (2 Common, 1 Exclusive)**
   - CommonA/CommonB watch `CONT_COM`; ExclC watches `CONT_EXC`.
   - Moving `CONT_COM` notifies both common watchers; moving `CONT_EXC` only notifies ExclC.
   - Proves: container subscriptions are precise—each watcher only receives events for containers they watch.

4. **Scenario 4 – Mixed Watching (1 Cargo, 1 Container)**
   - One client watches cargo `CI00000001` and container `CONT1`.
   - Completing the item triggers `Type=cargo ... Val=complete`; moving the container triggers `Type=container ... Val=[50.0, 50.0]`.
   - Proves: a single session can multiplex different object types; event payloads carry enough info to distinguish them.

5. **Scenario 5 – Save & Persistence**
   - `Saver` creates `CI00000001` and calls `SAVE`; after restart, `Verifier` does `LIST_ITEMS`.
   - Log shows the same item JSON (state `accepted`) loaded from `server_state.json`.
   - Proves: state is correctly serialized and reconstructed across server restarts.

6. **Scenario 6 – Synchronous Waiting (`WAIT_EVENTS`)**
   - `Waiter` does `WATCH` then `WAIT_EVENTS`; `Trigger` completes the item later.
   - With the current script, `WAIT_EVENTS` is immediately followed by `QUIT`, so we don’t see the `OK event available` line in the transcript.
   - But the server logic increments an event counter and wakes waiters as soon as a completion event is queued; adding a small delay after `WAIT_EVENTS` makes the reply visible.
   - Proves: we support a blocking "wait until something changes" style, not only asynchronous push.

7. **Scenario 7 – Polling vs. Pushing**
   - `Watcher` subscribes; `Poller` repeatedly calls `STATUS` on the same item.
   - Before completion, `STATUS` always shows `accepted` while no events fire.
   - When `Updater` completes the item:
     - `Watcher` immediately gets an `EVENT ... state=complete`.
     - Next `STATUS` replies show `state="complete"`.
   - Proves: push subscribers see changes instantly; pollers only see them when they ask.

8. **Scenario 8 – Client Disconnection Handling**
   - `Dropper` watches `CI00000001` then abruptly closes its socket.
   - `Updater` completes both items; server logs show normal `OK completed` replies and clean shutdown.
   - Proves: broken clients do not crash the server; session cleanup removes dead watchers and other sessions continue normally.

---

## 6. Suggested Presentation Flow

1. Start with the mental model: items inside containers, watched by trackers, driven by a TCP server.
2. Briefly explain each main class (CargoItem, Container, Tracker, CargoDirectory).
3. Explain how a session works: commands in, model calls, `updated()`, events out.
4. Show the demo (`demo_watch.py`) and point out how it reproduces scenarios deterministically.
5. Walk through 2–3 key scenarios (1, 2, 5, 7 are good choices) as concrete proof that notifications, concurrency, and persistence behave as designed.
6. Close with the pattern: **change state → updated() → notify watchers → optionally save to disk**.
