# Cargo Tracking Helpers

This repo now ships with a small executable harness so you can see the phase-one
classes in action without wiring up your own scripts or tests.

## Quick start

```powershell
# Run the scripted end-to-end flow
python demo.py

# Start the TCP service (Ctrl+C to stop, port defaults to 5000)
python server.py

# Custom port example
python server.py 6000
```

### Demo flow
`python run.py` creates a cargo item, loads it into a container, drives the
container to a new location, and prints the tracker snapshots so you can verify
the state changes manually.

### TCP/IP service
The server listens on the port you provide (default 5000) and accepts simple
newline-delimited commands. Arguments are split on spaces, so keep every value
single-word for now (e.g., avoid spaces inside descriptions). Available verbs:

- `HELP`, `PING`, `USER <name>`, `QUIT`
- `CREATE_ITEM <sender> <recipient> <address> <owner>`
- `CREATE_CONTAINER <cid> <description> <type> <lon> <lat>`
- `LIST_ITEMS`, `LIST_CONTAINERS`
- `STATUS <item_id>`, `LOAD <item_id> <container_id>`
- `WATCH <item_id>`, `WATCH_CONTAINER <cid>` to stream async updates
- `SETLOC <cid> <lon> <lat>` to move a container and trigger notifications

Every session spins up a notification thread that pushes `EVENT {...}` lines to
the socket whenever watched cargo items or containers change. Use `WATCH` or
`WATCH_CONTAINER` to subscribe to updates you care about. The optional `USER`
command lets the client tag themselves so events include the username.

## Running tests
There are two copies of each test file (top-level + `tests/` subfolder), which
confuses pytest if you run the entire tree at once. Invoke the top-level suites
explicitly:

```powershell
python -m pytest -q test_cargo_item.py test_container.py test_tracker.py
```
