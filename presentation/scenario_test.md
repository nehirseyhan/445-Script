============================================================
SCENARIO 1: Concurrent Updates (Race Condition)
============================================================
--- Starting Server ---
[UPDATER] >> CREATE_CONTAINER RACE_CONT Truck Truck 0 0
[UPDATER] RECV: OK hello Racer1
[UPDATER] RECV: OK hello Setup
[UPDATER] RECV: OK RACE_CONT
[UPDATER2] RECV: OK hello Racer2
[WATCH_A] RECV: OK hello Observer
[WATCH_A] >> WATCH_CONTAINER RACE_CONT
[WATCH_A] RECV: OK watching container RACE_CONT
[UPDATER] >> SETLOC RACE_CONT 10.0 10.0
[UPDATER] RECV: OK moved RACE_CONT
[WATCH_A] NOTIFICATION: Type=container ID=RACE_CONT Val=[10.0, 10.0]
[UPDATER2] >> SETLOC RACE_CONT 20.0 20.0
[UPDATER2] RECV: OK moved RACE_CONT
[WATCH_A] NOTIFICATION: Type=container ID=RACE_CONT Val=[20.0, 20.0]
--- Stopping Server ---

Scenario 1 – Concurrent Updates (Race Condition)
Goal: Demonstrate two clients racing to move the same container while one watcher listens for every movement.

What happens:
- Setup creates container RACE_CONT and the observer subscribes via WATCH_CONTAINER.
- Racer1 moves the container to (10,10) and the watcher receives an immediate container notification.
- Racer2 quickly overwrites the location to (20,20); the watcher receives the newer coordinates as a second notification.

Interpretation: The server serializes both SETLOC operations and pushes each resulting state to all subscribers, so watchers see the race play out in chronological order and the final position is the last update.

============================================================
SCENARIO 2: Item Watchers (2 Common, 1 Exclusive)
============================================================
--- Starting Server ---
[UPDATER] >> CREATE_ITEM S1 R1 A1 O1
[UPDATER] >> CREATE_ITEM S2 R2 A2 O2
[UPDATER] >> CREATE_ITEM S3 R3 A3 O3
[UPDATER] >> CREATE_CONTAINER TRUCK1 Truck Truck 0 0
[UPDATER] RECV: OK hello Updater
[UPDATER] RECV: OK CI00000001
[UPDATER] RECV: OK CI00000002
[UPDATER] RECV: OK CI00000003
[UPDATER] RECV: OK TRUCK1
[WATCH_A] RECV: OK hello CommonA
[WATCH_B] RECV: OK hello CommonB
[WATCH_C] RECV: OK hello ExclC
[WATCH_B] >> WATCH CI00000002
[WATCH_B] RECV: OK watching CI00000002
[WATCH_A] >> WATCH CI00000002
[WATCH_C] >> WATCH CI00000003
[WATCH_A] RECV: OK watching CI00000002
[WATCH_C] RECV: OK watching CI00000003
[UPDATER] >> LOAD CI00000002 TRUCK1
[UPDATER] >> LOAD CI00000003 TRUCK1
[UPDATER] RECV: OK loaded CI00000002 into TRUCK1
[WATCH_B] NOTIFICATION: Type=cargo ID=CI00000002 Val=in transit
[UPDATER] RECV: OK loaded CI00000003 into TRUCK1
[WATCH_C] NOTIFICATION: Type=cargo ID=CI00000003 Val=in transit
[WATCH_A] NOTIFICATION: Type=cargo ID=CI00000002 Val=in transit
[UPDATER] >> SETLOC TRUCK1 50 50
[UPDATER] RECV: OK moved TRUCK1
[WATCH_C] NOTIFICATION: Type=cargo ID=CI00000003 Val=in transit
[WATCH_A] NOTIFICATION: Type=cargo ID=CI00000002 Val=in transit
[WATCH_B] NOTIFICATION: Type=cargo ID=CI00000002 Val=in transit
[UPDATER] >> UNLOAD CI00000002
[UPDATER] RECV: OK unloaded CI00000002
[WATCH_B] NOTIFICATION: Type=cargo ID=CI00000002 Val=accepted
[WATCH_A] NOTIFICATION: Type=cargo ID=CI00000002 Val=accepted
[UPDATER] >> QUIT
[UPDATER] RECV: OK bye
--- Stopping Server ---

Scenario 2 – Item Watchers (2 Common, 1 Exclusive)
Goal: Show multiple clients watching two different cargo items, including redundant watchers on the same object.

What happens:
- Three cargo items plus container TRUCK1 are created; CommonA/CommonB watch CI00000002, ExclC watches CI00000003.
- Loading CI00000002 into TRUCK1 flips its state to in transit, producing identical notifications for both common watchers; loading CI00000003 does the same for the exclusive watcher.
- Moving TRUCK1 relays more in transit notifications because location changes propagate down to watched cargo.
- Unloading CI00000002 transitions it to accepted and both common watchers see the new terminal state.

Interpretation: Any watcher tied to an item receives every state transition, and redundant watchers simply get duplicate pushes without interfering with each other.

============================================================
SCENARIO 3: Container Watchers (2 Common, 1 Exclusive)
============================================================
--- Starting Server ---
[UPDATER] >> CREATE_ITEM S1 R1 A1 O1
[WATCH_A] RECV: OK hello CommonA
[UPDATER] >> CREATE_CONTAINER CONT_COM Truck Truck 0 0
[UPDATER] >> CREATE_CONTAINER CONT_EXC Truck Truck 1 1
[UPDATER] RECV: OK hello Updater
[UPDATER] RECV: OK CI00000001
[UPDATER] RECV: OK CONT_COM
[WATCH_B] RECV: OK hello CommonB
[UPDATER] RECV: OK CONT_EXC
[WATCH_C] RECV: OK hello ExclC
[WATCH_A] >> WATCH_CONTAINER CONT_COM
[WATCH_A] RECV: OK watching container CONT_COM
[WATCH_B] >> WATCH_CONTAINER CONT_COM
[WATCH_B] RECV: OK watching container CONT_COM
[WATCH_C] >> WATCH_CONTAINER CONT_EXC
[WATCH_C] RECV: OK watching container CONT_EXC
[UPDATER] >> LOAD CI00000001 CONT_COM
[UPDATER] RECV: OK loaded CI00000001 into CONT_COM
[UPDATER] >> SETLOC CONT_COM 50 50
[UPDATER] RECV: OK moved CONT_COM
[WATCH_A] NOTIFICATION: Type=container ID=CONT_COM Val=[50.0, 50.0]
[WATCH_B] NOTIFICATION: Type=container ID=CONT_COM Val=[50.0, 50.0]
[UPDATER] >> SETLOC CONT_EXC 99 99
[UPDATER] RECV: OK moved CONT_EXC
[WATCH_C] NOTIFICATION: Type=container ID=CONT_EXC Val=[99.0, 99.0]
[UPDATER] >> QUIT
[UPDATER] RECV: OK bye
--- Stopping Server ---

Scenario 3 – Container Watchers (2 Common, 1 Exclusive)
Goal: Validate container-level subscriptions with both shared and exclusive watchers.

What happens:
- CommonA and CommonB subscribe to CONT_COM, while ExclC watches CONT_EXC.
- Moving CONT_COM to (50,50) results in simultaneous notifications to both common watchers.
- Moving CONT_EXC fires a single update to ExclC, confirming isolation between watch groups.

Interpretation: Container watchers receive only the moves for the containers they track, and multiple watchers on the same container all get identical payloads.

============================================================
SCENARIO 4: Mixed Watching (1 Cargo, 1 Container)
============================================================
--- Starting Server ---
[UPDATER] >> CREATE_ITEM S1 R1 A1 O1
[UPDATER] >> CREATE_CONTAINER CONT1 Truck Truck 0 0
[UPDATER] RECV: OK hello Updater
[UPDATER] RECV: OK CI00000001
[UPDATER] RECV: OK CONT1
[WATCH_A] RECV: OK hello MixedWatcher
[WATCH_A] >> WATCH CI00000001
[WATCH_A] >> WATCH_CONTAINER CONT1
[WATCH_A] RECV: OK watching CI00000001
[WATCH_A] RECV: OK watching container CONT1
[UPDATER] >> COMPLETE CI00000001
[UPDATER] RECV: OK completed CI00000001
[WATCH_A] NOTIFICATION: Type=cargo ID=CI00000001 Val=complete
[UPDATER] >> SETLOC CONT1 50 50
[UPDATER] RECV: OK moved CONT1
[WATCH_A] NOTIFICATION: Type=container ID=CONT1 Val=[50.0, 50.0]
[UPDATER] >> QUIT
[UPDATER] RECV: OK bye
--- Stopping Server ---

Scenario 4 – Mixed Watching (1 Cargo, 1 Container)
Goal: Show that one client can watch heterogeneous objects over a single socket.

What happens:
- MixedWatcher issues WATCH for CI00000001 and WATCH_CONTAINER for CONT1.
- Completing the cargo triggers a cargo notification with state complete.
- Moving the container to (50,50) produces a separate container notification, delivered to the same client.

Interpretation: Sessions can multiplex several watch targets; events are tagged so the client can distinguish cargo versus container updates.

============================================================
SCENARIO 5: Save & Persistence
============================================================
--- Starting Server ---
[UPDATER] >> CREATE_ITEM SavedItem Recip Addr Owner
[UPDATER] >> SAVE
[UPDATER] RECV: OK hello Saver
[UPDATER] RECV: OK CI00000001
[UPDATER] RECV: OK saved
[UPDATER] >> QUIT
[UPDATER] RECV: OK bye
--- Stopping Server (Keeping State) ---
--- Restarting Server ---
[VERIFIER] >> LIST_ITEMS
[VERIFIER] RECV: OK hello Verifier
[VERIFIER] DATA DUMP: ["{\"container\": null, \"deleted\": false, \"id\": \"CI00000001\", \"owner\": \"Owner\", \"recipaddr\": \"Addr\", \"recipnam\": \"Recip\", \"sendernam\": \"SavedItem\", \"state\": \"accepted\"}"]
[VERIFIER] >> QUIT
[VERIFIER] RECV: OK bye
--- Stopping Server ---

Scenario 5 – Save & Persistence
Goal: Prove that SAVE writes durable state that survives process restarts.

What happens:
- Saver creates CI00000001 and calls SAVE; the server acknowledges persistence.
- After shutting down without deleting the state file, the server restarts and LIST_ITEMS returns the saved item JSON with state accepted.

Interpretation: SAVE correctly serializes both cargo metadata and state so the next server process can reconstruct it.

============================================================
SCENARIO 6: Synchronous Waiting (WAIT_EVENTS)
============================================================
--- Starting Server ---
[UPDATER] >> CREATE_ITEM S1 R1 A1 O1
[UPDATER] RECV: OK hello Setup
[UPDATER] RECV: OK CI00000001
[WATCH_A] RECV: OK hello Waiter
[UPDATER2] RECV: OK hello Trigger
[WATCH_A] >> WATCH CI00000001
[WATCH_A] RECV: OK watching CI00000001
[WATCH_A] >> WAIT_EVENTS
[WATCH_A] >> QUIT
[UPDATER] >> QUIT
[UPDATER] RECV: OK bye
[UPDATER2] >> COMPLETE CI00000001
[UPDATER2] >> QUIT
[UPDATER2] RECV: OK completed CI00000001
[UPDATER2] RECV: OK bye
--- Stopping Server ---

Scenario 6 – Synchronous Waiting (WAIT_EVENTS)
Goal: Ensure WAIT_EVENTS blocks until an event is generated or the timeout lapses.

What happens:
- Waiter watches CI00000001 and issues WAIT_EVENTS; Trigger later completes the item.
- Because the script immediately queues QUIT after WAIT_EVENTS, the session closes before the completion arrives, so the transcript shows no response line for the wait.

Interpretation: With the new server logic, WAIT_EVENTS holds the connection open until a fresh event increments the session counter. To observe the `OK event available` reply, keep the client connected (e.g., add a sleep after WAIT_EVENTS) so the completion arrives before QUIT.

============================================================
SCENARIO 7: Polling vs. Pushing
============================================================
--- Starting Server ---
[UPDATER] >> CREATE_ITEM S1 R1 A1 O1
[POLLER] RECV: OK hello Poller
[UPDATER] RECV: OK hello Setup
[UPDATER] RECV: OK CI00000001
[WATCH_A] RECV: OK hello Watcher
[UPDATER2] RECV: OK hello Updater
[UPDATER] >> QUIT
[UPDATER] RECV: OK bye
[POLLER] >> STATUS CI00000001
[WATCH_A] >> WATCH CI00000001
[POLLER] RECV: OK {"container": null, "deleted": false, "id": "CI00000001", "owner": "O1", "recipaddr": "A1", "recipnam": "R1", "sendernam": "S1", "state": "accepted"}
[WATCH_A] RECV: OK watching CI00000001
[POLLER] >> STATUS CI00000001
[POLLER] RECV: OK {"container": null, "deleted": false, "id": "CI00000001", "owner": "O1", "recipaddr": "A1", "recipnam": "R1", "sendernam": "S1", "state": "accepted"}
[UPDATER2] >> COMPLETE CI00000001
[UPDATER2] >> QUIT
[POLLER] >> STATUS CI00000001
[WATCH_A] NOTIFICATION: Type=cargo ID=CI00000001 Val=complete
[UPDATER2] RECV: OK completed CI00000001
[POLLER] RECV: OK {"container": null, "deleted": false, "id": "CI00000001", "owner": "O1", "recipaddr": "A1", "recipnam": "R1", "sendernam": "S1", "state": "complete"}
[UPDATER2] RECV: OK bye
[POLLER] >> STATUS CI00000001
[POLLER] >> QUIT
[POLLER] RECV: OK {"container": null, "deleted": false, "id": "CI00000001", "owner": "O1", "recipaddr": "A1", "recipnam": "R1", "sendernam": "S1", "state": "complete"}
[POLLER] RECV: OK bye
[WATCH_A] >> QUIT
[WATCH_A] RECV: OK bye
--- Stopping Server ---

Scenario 7 – Polling vs. Pushing
Goal: Contrast passive watchers against active pollers on the same item.

What happens:
- Watcher subscribes to CI00000001 while Poller repeatedly issues STATUS calls.
- STATUS replies show accepted until Updater completes the item; the watcher receives an immediate push with state complete.
- Subsequent STATUS calls now return state complete, confirming the poller only sees changes on demand.

Interpretation: Push subscribers receive events as soon as the state flips, while pollers must continuously request STATUS to observe the same transitions.

============================================================
SCENARIO 8: Client Disconnection Handling
============================================================
--- Starting Server ---
[UPDATER] >> CREATE_ITEM S1 R1 A1 O1
[UPDATER] >> CREATE_ITEM S2 R2 A2 O2
[UPDATER] RECV: OK hello Setup
[UPDATER] RECV: OK CI00000001
[UPDATER] RECV: OK CI00000002
[WATCH_A] RECV: OK hello Dropper
[UPDATER2] RECV: OK hello Updater
[UPDATER] >> QUIT
[UPDATER] RECV: OK bye
[WATCH_A] >> WATCH CI00000001
[WATCH_A] RECV: OK watching CI00000001
[WATCH_A] >> Abruptly closing socket!
[UPDATER2] >> COMPLETE CI00000001
[UPDATER2] >> COMPLETE CI00000002
[UPDATER2] RECV: OK completed CI00000001
[UPDATER2] RECV: OK completed CI00000002
[UPDATER2] >> QUIT
[UPDATER2] RECV: OK bye
--- Stopping Server ---

Scenario 8 – Client Disconnection Handling
Goal: Verify the server cleans up watchers when a client drops unexpectedly.

What happens:
- Dropper watches CI00000001 and then closes the socket without QUIT.
- Updater completes both items; despite the stale watcher, the server processes the updates and shuts down normally.

Interpretation: Notification delivery failures simply remove the session; other clients continue unaffected and no crash occurs.