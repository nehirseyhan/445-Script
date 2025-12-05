# Design Decisions – Server and Demo Watch

This document explains **why** the important design decisions in `cargo_item.py`, `container.py`, `tracker.py`, `server.py` and `demo_watch.py` were made. The goal is to make every choice easy to justify in a grading discussion.

---

## 1. Domain Objects (`cargo_item.py`, `container.py`, `tracker.py`)

### 1.1 `CargoItem` and `CargoDirectory`
- **What:**
  - `CargoItem` represents one package with sender / recipient / address / owner, a generated tracking id and a life‑cycle state.
  - `CargoDirectory` is an in‑memory registry that owns all `CargoItem` instances and provides CRUD‑style operations.
- **Why this split:**
  - `CargoItem` focuses on **business rules for a single item** (validation, state, notifications).
  - `CargoDirectory` focuses on **collection‑level concerns** (id → object map, attached users, deletion constraints).
- **Important decisions:**
  - Constructor validates every required text field and fails fast with clear messages (e.g. "sendernam not provided").
  - Tracking ids are generated once using a global counter and stored as a string like `CI00000001` so they are easy to read in logs and protocol.
  - `get()` always returns a **single JSON snapshot** for the item (id, sender/recipient, address, owner, state, container id and deleted flag). The server reuses this instead of re‑serializing fields in multiple places.
  - `update(**updates)` uses `_allowed_update_fields` to map the protocol keys (e.g. `sendernam`, `recipnam`) to internal attributes and rejects unknown or empty values. This prevents silent typos in commands and keeps validation centralized.
  - `delete()` marks the item as deleted, clears its container link, forces state to `deleted`, calls `updated()` once, and then clears all trackers. Deleting from the directory always goes through the model logic instead of just popping from the dict.

### 1.2 Container state and location (`Container`)
- **What:**
  - `Container` represents either a stationary or a mobile holder for items (`FrontOffice`, `Hub`, `Truck`, …).
  - It stores the id, description, type, current `(lon, lat)` location, a set of items it holds, and a set of trackers attached to the container itself.
- **Why map container type to item state:**
  - The same `CargoItem` state should reflect where it is:
    - In a stationary container (`FrontOffice`, `Hub`) → item state is logically `waiting`.
    - In a moving container (e.g. trucks) → item state is `in transit`.
  - This logic lives in `Container.getState()` and is consumed by `CargoItem.setContainer()`, so all state transitions go through **one place** instead of being duplicated in the server.
- **Location updates:**
  - `setlocation(long, latt)` validates numeric input and only triggers `updated()` when the location actually changes.
  - `updated()` notifies attached trackers and then iterates over every contained item and calls `item.updated()`. This ensures that **location changes of a container propagate to item‑level watchers**.
- **Load / unload / move:**
  - `load(itemlist)` inserts each item into the container set and then calls `item.setContainer(self)` so the item’s own state and notifications are responsible for informing trackers.
  - `unload(itemlist)` removes items and calls `item.setContainer(None)`, which typically returns the state to `accepted` unless the item is already complete.
  - `move(itemlist, newcontainer)` is a convenience that unloads from this container and loads into another one, still using `item.setContainer` so state and events stay consistent.

### 1.3 Tracker as a reusable observer (`Tracker`)
- **What:**
  - `Tracker` is a generic observer object that can watch multiple `CargoItem` and `Container` instances.
  - It has an optional rectangular view filter and an optional callback `on_update` used by phase‑2 server sessions.
- **Why reuse the same pattern everywhere:**
  - Domain objects (`CargoItem`, `Container`) only need to know that a watcher has an `updated()` method; they do **not** know or care if it is an in‑process `Tracker` or a network‑driven session tracker.
  - This keeps the model decoupled from I/O and lets the server plug in its own watcher (`Tracker` with `on_update`) without changing the model code.
- **View rectangle and filtering:**
  - The tracker can ignore updates that are outside a configured rectangle by examining the location of a container or of an item’s container.
  - This anticipates real‑world use cases (map view windows) and keeps the filtering logic in one place instead of scattering `if in_view` checks throughout the code.

---

## 2. Global Model and Lock in `server.py`

### 1.1 Global `_directory` and `_containers`
- **What:**
  - `_directory = CargoDirectory()` holds **all cargo items**.
  - `_containers = {}` holds **all containers**, keyed by `cid`.
- **Why:**
  - The server must share **one common world** between all clients; if each session had its own directory, clients would not see each other’s changes.
  - Using globals makes it clear that there is **only one copy** of the model in this process.

### 2.1 `_model_lock = RLock()`
- **What:** A re‑entrant lock guarding all access to `_directory` and `_containers`.
- **Why a lock at all?**
  - Each client connection runs in its own `Session` thread.
  - Two clients can send commands at the same time (for example two `SETLOC` commands in scenario 1).
  - Without a lock, Python could interleave operations in the middle of updates, leading to **corrupted state** or lost updates.
- **Why `RLock` (re‑entrant) instead of a normal `Lock`?**
  - Some calls can be nested. For example, a command in `Session.handle()` acquires `_model_lock`, then calls methods that may indirectly call other code that also wants the lock.
  - With a basic lock this would deadlock if the same thread tried to re‑acquire it; `RLock` allows the same thread to enter multiple times safely.

---

## 3. Persistence Design (`save_state` / `load_state`)

### 3.1 Why JSON files (`server_state.json`)?
- **Simple** to inspect by hand (useful for debugging and grading).
- **Portable**: no database, no external dependency, just read/write a text file.
- **Enough** for our data size: items and containers are few.

### 3.2 `save_state(path=STATE_FILE)`
- **Locks the model:**
  - `with _model_lock:` ensures we read a **consistent snapshot**:
    - No other thread can modify items or containers halfway through saving.
- **Uses existing `get()` methods then `json.loads`:**
  - We already have `CargoItem.get()` and `Container.get()` that return JSON.
  - Instead of re‑serializing from scratch, we reuse them and do `json.loads` to get dicts.
  - This keeps **all fields in one place** (those methods) so we don’t accidentally forget a field.
- **Writes one combined dict:**
  - `{"items": [...], "containers": [...]}` instead of separate files.
  - Easier to manage one file, and loading is simple: open once, parse once.

### 3.3 `load_state(path=STATE_FILE)`
- **Check `os.path.exists(path)` first:**
  - Avoids raising an error when starting for the very first time when there is no state file yet.
- **Handles `json.JSONDecodeError` and `OSError`:**
  - If the file is corrupted or partially written, the server does **not crash**; it just prints a warning and continues with an empty model.
  - This is important because crashes on startup are hard to diagnose in demos.
- **Rebuilds objects instead of storing them directly:**
  - We create fresh `CargoDirectory` and fresh `Container` objects from the stored payload.
  - This avoids mixing old in‑memory state with new data and keeps initialization clean.
- **Build containers first, then items:**
  - Items refer to containers by id.
  - We must have all containers ready before we can correctly set each item’s `_container` and `_container_id`.
- **Resets the ID counter (`CargoItem._id_sequence`):**
  - We compute the largest numeric suffix and set the global counter to `max + 1`.
  - This avoids reusing old tracking ids after a restart.

---

## 4. Session and Tracker Design in `server.py`

### 4.1 `Session` per client connection
- **What:** Each accepted TCP connection gets its own `Session` thread.
- **Why:**
  - Simple mental model: “**one client = one thread**”.
  - No need for asynchronous I/O or event loops; the OS thread handles blocking `recv()` and `send()` calls.

### 4.2 Session‑level tracker and callback
- **What:** Each `Session` owns a `Tracker` instance with its `on_update` callback bound to the session method `_on_tracker_update`.
- **Why not a custom watcher type:**
  - The same `Tracker` abstraction is now reused both for phase‑1 console tracking and for phase‑2 network tracking.
  - Items and containers always talk to a `Tracker` and call `track(self)` / `untrack(self)`; the **only difference** is what the concrete tracker does in its `updated()` implementation.
- **Callback design:**
  - `_on_tracker_update(self, tracker_obj, updated_object, obj_id)` converts a high‑level domain update into a compact event record `(kind, id, value)` and appends it into the session’s internal event queue.
  - For cargo items it stores `("cargo", trackingId, state)`, for containers `("container", cid, loc)`, and it can also record tracker updates.

### 4.3 Event queue and condition variable in `Session`
- **Data:**
  - `events`: list of pending events.
  - `cond`: `Condition` used to coordinate between threads.
  - `pending_events`, `_event_counter`: counters to track how many events and whether something changed.
- **Why a queue instead of sending directly in the tracker callback:**
  - `Tracker.updated()` may be called from **model code** holding `_model_lock`.
  - Sending to the socket from there could block (for example, slow or dead client), which would **block all other clients** waiting for the lock.
  - Putting events into a queue is quick; then a dedicated thread (`notificationagent`) actually sends them.
- **Why a condition variable:**
  - When there are no events, the notification thread waits on `cond` instead of busy‑looping (spinning and wasting CPU).
  - When the session tracker callback adds an event, it signals the condition, waking the notifier.

### 4.4 `notificationagent(session)` thread
- **What:** A thread per session that sends `EVENT` lines.
- **Loop design:**
  - It waits while `session.events` is empty **and** the session is still running.
  - If session stops and there are no events, it quits.
- **Why manage `pending_events` and `_event_counter`:**
  - `pending_events` provides a simple count for session logic (e.g., to know when all events have been flushed).
  - `_event_counter` is used by the `WAIT_EVENTS` command to know if **any new event** has happened since the last check.
- **Error handling:**
  - If sending fails, it marks `session._running = False` and breaks.
  - This avoids infinite loops writing to a dead socket.

### 4.5 `Session.run()` (command loop)
- **Buffering logic:**
  - Reads raw bytes from the socket and appends to `_buffer`.
  - Processes complete lines (split by `\n`) one by one.
  - This supports **multiple commands coming in one TCP chunk** or being split across chunks.
- **Stopping conditions:**
  - If `recv()` returns empty bytes, remote closed → break.
  - If `handle()` returns `cont = False` (e.g., after `QUIT`), stop loop.
- **Exception handling around `handle()`:**
  - Wraps `handle()` in `try/except` and returns `ERR ...` messages to the client.
  - Keeps the session alive on command errors instead of killing the connection.

### 4.6 `Session.handle()` – command design

For each command we combine **input validation**, **protected model access**, and **clear messages**.

- **Common patterns:**
  - Check argument count and raise `ValueError` with a clear usage message (helps both users and tests).
  - Use `with _model_lock:` for all reads/modifications of items and containers.
  - Always `return ("OK ...", True/False)` or raise an exception; the outer loop converts exceptions to `ERR ...`.

Some specific choices:

- `HELP`
  - Returns a **single summarizing line** describing all commands; simple for a human to read in a terminal.

- `CREATE_ITEM` and `CREATE_CONTAINER`
  - Argument count is strictly checked so we cannot accidentally accept wrong data.
  - For containers, we check if `cid` is already in `_containers` to prevent duplicates, then create.

- `LIST_ITEMS` / `LIST_CONTAINERS`
  - For `LIST_ITEMS`, we reuse `CargoDirectory.list()`, which already serializes items.
  - For containers, we call `cont.get()` for each and parse to dicts, then return a JSON list.
  - `OK ` prefix allows client to easily distinguish success from errors.

- `WATCH` / `WATCH_CONTAINER`
  - We look up the item or container once inside the lock; if not found, we raise a `KeyError` with a clear message.
  - We call `track(self.watcher)` to reuse the same tracking interface used by the plain `Tracker` class.
  - We also store the objects in `session.tracked_items` / `session.tracked_containers` so `close()` can unregister properly later.

- `LOAD`
  - Verifies that both the item and container exist.
  - Checks if the item is already in another container and refuses to silently move it; this **avoids hidden side effects**.
  - If already in the requested container, returns a friendly "already in" message instead of failing.
  - Otherwise, calls `cont.load([item])`, which centralizes all the state change and notifications in the `Container` class.

- `SETLOC`
  - Uses `float(args[1])` and `float(args[2])` to ensure coordinates are numeric.
  - Any `ValueError` becomes an exception and the caller sees an `ERR` line.

- `UNLOAD` / `COMPLETE`
  - For `UNLOAD`, we require the item to be in a container; otherwise we return an error instead of silently succeeding.
  - For `COMPLETE`, if the item is already `complete`, we return a message saying that rather than re‑executing.
  - Both operations rely on the domain methods (`cont.unload`, `item.complete`) so that **business rules stay in one place**.

- `STATUS`
  - Returns `item.get()` exactly, so server does not manually assemble JSON. This avoids data drift.

- `WAIT_EVENTS`
  - Uses `self._event_counter` to detect **any change** in the event queue, not just count.
  - Waits up to a fixed timeout (5 seconds), so we never risk blocking a client forever.
  - Returns a plain, human‑readable message: `"OK event available"` or `"OK no pending events"`.
  - This choice keeps the semantics **simple** for the caller: “did something happen in that window?”

- `SAVE`
  - Just calls `save_state()`; we keep persistence logic centralized.

- `QUIT`
  - Returns `OK bye` and a flag `False`, telling the loop to end.
  - The actual cleanup (closing socket, unregistering watchers) is done in `close()` to keep things consistent.

### 4.7 `Session.close()` design
- **Why unregister watchers here:**
  - Items and containers hold references to trackers.
  - If a session died but stayed registered, any `updated()` on those objects would try to notify an invalid session tracker → errors or memory leaks.
  - `close()` iterates over `tracked_items` and `tracked_containers` and calls `untrack(self.watcher)` in a best‑effort way.
- **Why put socket close inside `try/except`:**
  - The socket might already be closed; we don’t want cleanup to raise new exceptions.

### 4.8 `if __name__ == '__main__':` server entrypoint
- **Port parsing:**
  - We try to parse an integer from command‑line; on error, we fall back to 5000 and print a warning.
  - This gives some flexibility while staying robust.
- **`load_state()` before starting:**
  - So that restarting the server brings back previous items and containers.
- **Accept loop:**
  - `while True: accept(); start Session thread` is the simplest way to handle multiple simultaneous clients.
- **`finally: serversocket.close(); save_state()`**
  - Ensures that even on unexpected exit we close the listening socket and persist the last known state.

---

## 5. Design Decisions in `demo_watch.py`

### 4.1 Purpose of `demo_watch.py`
- **Why not manual testing only?**
  - Complex, concurrent behavior (multiple clients, race conditions, disconnects) is hard to reproduce manually.
  - The demo script lets us **replay** interesting scenarios reliably.
- **Why in the same language (Python) as the server:**
  - Easy to spawn the server process using `subprocess.Popen`.
  - Easy to reuse the same text protocol from a small client class (`DemoClient`).

### 5.2 Global config and colors
- `HOST`, `PORT`, and `STATE_FILE` are defined once at the top.
- `COLORS` is a simple mapping from a tag to an ANSI color code.
- **Why colors:**
  - Multiple clients write to the same terminal.
  - Colors make it easy to follow which log line belongs to which logical client or role (UPDATER, WATCH_A, etc.).

### 5.3 `log(tag, message)` helper
- **What:** Wraps prints with color and a tag like `[WATCH_A]`.
- **Why:**
  - Keeps `print` calls consistent and readable.
  - If we want to change formatting, we change it in one place.

### 5.4 `DemoClient` design

#### 5.4.1 Thread subclass
- **Why `threading.Thread` subclass:**
  - Each demo client behaves like a real user: it has its own connection and timeline.
  - We want them to run **in parallel** to reproduce races and mixed interactions.

#### 5.4.2 `connect()` with retries
- Tries up to 5 times, waiting 0.5 seconds between attempts.
- **Why:**
  - After starting the server process, it may take a bit of time before it starts listening.
  - Instead of failing immediately, we give the server time to come up.
  - After several failed attempts, we log an error and stop that client.

#### 5.4.3 `send(cmd)`
- Checks `self.running` and `self.sock` before trying to send.
- **Why:**
  - Prevents exceptions when the socket was closed due to previous errors.
  - Keeps discouraged commands from a “dead” client from causing noise.

#### 5.4.4 Action script design in `run()`
- Each `DemoClient` is configured with a list of `actions`.
- In the loop:
  - If action is a **number** → `time.sleep(action)`.
  - If action is a **string**:
    - If it equals `"__CLOSE_SOCKET__"` → we simulate a crash (abrupt close without `QUIT`).
    - Otherwise, we log and send it as a command.
- **Why mix numbers and strings in the same list:**
  - Very compact way to express a scenario timeline (commands and delays) in a single ordered list.
  - Easy to read: `[1.0, "WATCH ...", 5.0, "QUIT"]` reads like a script.

#### 5.4.5 Listener thread
- A separate `listen` thread per demo client receives data from the server.
- **Why separate from `run()`:**
  - Real network clients need to be able to **receive and send at the same time**.
  - While `run()` is sleeping or sending commands at specific moments, incoming `EVENT` and `OK` messages still arrive concurrently.

#### 5.4.6 Parsing server output in `listen()`
- We build a `buffer` and extract lines by `\n` to handle partial/incomplete reads.
- For each line:
  - If it starts with `"EVENT"`:
    - We parse the JSON part and log: type, id, value.
  - If it starts with `"OK ["`:
    - It’s likely a list (from `LIST_ITEMS` or `LIST_CONTAINERS`) → label as `DATA DUMP`.
  - If `"ERR"` → log clearly as an error.
  - Else if `"OK"` → generic response.
- **Why parse instead of blindly printing:**
  - For the demo, we want to **see the structure** of events, not just raw text.
  - This helps us visually verify that notifications are sent to the correct clients.

### 5.5 Starting and stopping the server

#### 5.5.1 `start_server()`
- Removes `STATE_FILE` if it exists.
- Starts `server.py` with `subprocess.Popen`, capturing stdout/stderr.
- Sleeps 1 second.
- **Why clean up the state file here:**
  - For many scenarios we want a **fresh, empty world**.
  - Old items/containers from previous runs would make behavior harder to reason about.
- **Why wait 1 second:**
  - Give the server time to bind the port so that demo clients don’t hit connection refused on the first try.

#### 5.5.2 `stop_server(proc)`
- Kills the server process and waits for it to exit.
- Again removes `STATE_FILE` if it exists.
- **Why `kill()` instead of graceful shutdown:**
  - The demo code already covers graceful shutdown in other scenarios.
  - For test script simplicity, forcibly terminating is enough.

### 5.6 Scenario‑specific choices

Each scenario is a **focused test** of one or two ideas rather than trying to test everything at once.

#### 5.6.1 Scenario 1 – Concurrent Updates
- Two clients set the same container location 50ms apart.
- **Why 50ms:**
  - Short enough that updates truly overlap.
  - Long enough that the order still matters and is visible in logs.

#### 5.6.2 Scenario 2 – Item Watchers
- Two watchers on the same item plus one on another.
- **Why:**
  - To show that **multiple independent sessions** can subscribe to the same item and all receive events.
  - Also to show that container‑level changes (like `SETLOC`) propagate to the items.

#### 5.6.3 Scenario 3 – Container Watchers
- Similar to scenario 2, but watchers are attached to containers.
- **Why separate scenario:**
  - Container watching is conceptually different (changes are about location, not item state itself).

#### 5.6.4 Scenario 4 – Mixed Watching
- One client watches both an item and a container.
- **Why:**
  - Demonstrates that a single session can receive **two types of notifications** at once.

#### 5.6.5 Scenario 5 – Save & Persistence
- First run: creates item + `SAVE` + stop.
- Second run: restarts server and `LIST_ITEMS`.
- **Why two phases:**
  - Proves that the model is written to and read from disk correctly, independent of a single server run.

#### 5.6.6 Scenario 6 – `WAIT_EVENTS`
- One client waits with `WAIT_EVENTS`, another triggers an update.
- **Why:**
  - Shows the **synchronous** side of the notification system (wait until something happens) instead of just async pushes.

#### 5.6.7 Scenario 7 – Poll vs Push
- One client watches (push), another polls `STATUS` (pull).
- **Why separate these:**
  - Highlights that the same system supports both usage patterns:
    - Passive listening.
    - Active polling.

#### 5.6.8 Scenario 8 – Disconnection Handling
- One watcher disconnects abruptly, another client continues to update.
- **Why:**
  - To show that the server remains stable when clients do not close politely.
  - Exercises `Session.close()` and `notificationagent` error handling in practice.

---

## 6. How to Talk About These Decisions

- Always link a **code pattern** to a **simple reason**:
  - "We use a lock so two clients cannot corrupt shared state."
  - "We use a background thread for notifications so item updates never block on a slow socket."
  - "We script scenarios instead of manual testing so we can reliably show concurrency and failures."
- If asked "Why not X?", map it to:
  - Simplicity for a homework project.
  - Predictable behavior in demos.
  - Reuse of existing domain logic (keeping rules in one place).

This should give you enough material to clearly explain the **why** behind almost every non‑trivial line in `server.py` and `demo_watch.py`. If you need even more detail for a specific function, we can extend this document for that part.