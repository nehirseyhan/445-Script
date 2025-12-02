import socket
import threading
import time
import sys
import subprocess
import os
import json

# Configuration
HOST = 'localhost'
PORT = 5000
STATE_FILE = 'server_state.json'

# ANSI Colors for nicer output
COLORS = {
    'RESET': '\033[0m',
    'SERVER': '\033[90m',  # Gray
    'UPDATER': '\033[95m', # Magenta
    'UPDATER2': '\033[91m',# Red
    'WATCH_A': '\033[94m', # Blue
    'WATCH_B': '\033[96m', # Cyan
    'WATCH_C': '\033[92m', # Green
    'VERIFIER': '\033[93m', # Yellow
    'POLLER': '\033[33m',   # Orange/Yellow
}

def log(tag, message):
    color = COLORS.get(tag, COLORS['RESET'])
    print(f"{color}[{tag}] {message}{COLORS['RESET']}")

class DemoClient(threading.Thread):
    def __init__(self, name, tag, actions):
        super().__init__()
        self.name = name
        self.tag = tag
        self.actions = actions
        self.sock = None
        self.running = True

    def connect(self):
        for i in range(5): # Retry up to 5 times
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.connect((HOST, PORT))
                self.send(f"USER {self.name}")
                return # Success
            except Exception as e:
                if i == 4: # Last attempt
                    log(self.tag, f"Connection failed after multiple retries: {e}")
                    self.running = False
                else:
                    time.sleep(0.5) # Wait before retrying

    def send(self, cmd):
        if not self.running or not self.sock:
            return
        try:
            self.sock.sendall((cmd + "\n").encode('utf-8'))
        except Exception as e:
            log(self.tag, f"Send failed: {e}")

    def run(self):
        self.connect()
        
        listener = threading.Thread(target=self.listen)
        listener.daemon = True
        listener.start()

        for action in self.actions:
            if not self.running:
                break
            
            if isinstance(action, (int, float)):
                time.sleep(action)
            elif isinstance(action, str):
                if action == "__CLOSE_SOCKET__":
                    log(self.tag, ">> Abruptly closing socket!")
                    self.sock.close()
                    self.sock = None
                    self.running = False
                    break
                
                log(self.tag, f">> {action}")
                self.send(action)
        
        # specific delay to allow last responses to come in
        if self.running:
            time.sleep(1.0)
            
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except:
                pass

    def listen(self):
        buffer = ""
        while self.running and self.sock:
            try:
                data = self.sock.recv(4096)
                if not data:
                    break
                buffer += data.decode('utf-8', errors='ignore')
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    line = line.strip()
                    if not line: continue
                    
                    if line.startswith("EVENT"):
                        try:
                            json_part = line[6:]
                            evt = json.loads(json_part)
                            obj_data = evt.get('obj', [])
                            log(self.tag, f"NOTIFICATION: Type={obj_data[0]} ID={obj_data[1]} Val={obj_data[2]}")
                        except:
                            log(self.tag, f"RECV: {line}")
                    elif line.startswith("OK ["):
                        log(self.tag, f"DATA DUMP: {line[3:]}")
                    elif line.startswith("ERR"):
                        log(self.tag, f"ERROR: {line}")
                    elif line.startswith("OK"):
                        log(self.tag, f"RECV: {line}")
            except Exception:
                break

def start_server():
    # Cleanup state for clean start
    if os.path.exists(STATE_FILE):
        try: os.remove(STATE_FILE)
        except OSError: pass

    print("--- Starting Server ---")
    proc = subprocess.Popen(
        [sys.executable, 'server.py'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    time.sleep(1) 
    return proc

def stop_server(proc):
    print("--- Stopping Server ---")
    proc.kill()
    proc.wait()
    if os.path.exists(STATE_FILE):
        try: os.remove(STATE_FILE)
        except OSError: pass

def run_scenario_1_concurrency():
    # 1. Two updaters updating at the same time
    print(f"\n{'='*60}\nSCENARIO 1: Concurrent Updates (Race Condition)\n{'='*60}")
    
    server = start_server()
    try:
        # Setup container
        setup = ["CREATE_CONTAINER RACE_CONT Truck Truck 0 0", 2.0]
        
        # Two clients trying to set different locations at the same time
        updater1 = [2.0, "SETLOC RACE_CONT 10.0 10.0"]
        updater2 = [2.05, "SETLOC RACE_CONT 20.0 20.0"] # 50ms difference
        
        watcher = [1.0, "WATCH_CONTAINER RACE_CONT", 5.0]

        clients = [
            DemoClient("Setup", "UPDATER", setup),
            DemoClient("Racer1", "UPDATER", updater1),
            DemoClient("Racer2", "UPDATER2", updater2),
            DemoClient("Observer", "WATCH_A", watcher)
        ]
        
        for c in clients: c.start()
        for c in clients: c.join()
    finally:
        stop_server(server)

def run_scenario_2_item_watchers():
    # 2. 3 watchers (2 common, 1 exclusive cargo) - Load/Unload/SetLoc
    print(f"\n{'='*60}\nSCENARIO 2: Item Watchers (2 Common, 1 Exclusive)\n{'='*60}")
    
    server = start_server()
    try:
        setup = [
            "CREATE_ITEM S1 R1 A1 O1", # CI...01
            "CREATE_ITEM S2 R2 A2 O2", # CI...02 (Common)
            "CREATE_ITEM S3 R3 A3 O3", # CI...03 (Exclusive)
            "CREATE_CONTAINER TRUCK1 Truck Truck 0 0",
            4.0, 
            "LOAD CI00000002 TRUCK1",
            "LOAD CI00000003 TRUCK1",
            1.0,
            "SETLOC TRUCK1 50 50", # Should trigger item updates
            1.0,
            "UNLOAD CI00000002",
            1.0,
            "QUIT"
        ]

        # Common Watchers (Watch Item 2)
        w1 = [1.5, "WATCH CI00000002", 10.0]
        w2 = [1.5, "WATCH CI00000002", 10.0]
        # Exclusive Watcher (Watch Item 3)
        w3 = [1.5, "WATCH CI00000003", 10.0]

        clients = [
            DemoClient("Updater", "UPDATER", setup),
            DemoClient("CommonA", "WATCH_A", w1),
            DemoClient("CommonB", "WATCH_B", w2),
            DemoClient("ExclC", "WATCH_C", w3),
        ]
        for c in clients: c.start()
        for c in clients: c.join()
    finally:
        stop_server(server)

def run_scenario_3_container_watchers():
    # 3. 3 watchers (2 common, 1 exclusive container) - Load/Unload/SetLoc
    print(f"\n{'='*60}\nSCENARIO 3: Container Watchers (2 Common, 1 Exclusive)\n{'='*60}")
    
    server = start_server()
    try:
        setup = [
            "CREATE_ITEM S1 R1 A1 O1",
            "CREATE_CONTAINER CONT_COM Truck Truck 0 0", # Common
            "CREATE_CONTAINER CONT_EXC Truck Truck 1 1", # Exclusive
            4.0,
            "LOAD CI00000001 CONT_COM", # Loading items typically Item Watchers, not Container Watchers 
            1.0,
            "SETLOC CONT_COM 50 50", # Should notify Common watchers
            1.0,
            "SETLOC CONT_EXC 99 99", # Should notify Exclusive watcher
            1.0,
            "QUIT"
        ]

        w1 = [1.5, "WATCH_CONTAINER CONT_COM", 10.0]
        w2 = [1.5, "WATCH_CONTAINER CONT_COM", 10.0]
        w3 = [1.5, "WATCH_CONTAINER CONT_EXC", 10.0]

        clients = [
            DemoClient("Updater", "UPDATER", setup),
            DemoClient("CommonA", "WATCH_A", w1),
            DemoClient("CommonB", "WATCH_B", w2),
            DemoClient("ExclC", "WATCH_C", w3),
        ]
        for c in clients: c.start()
        for c in clients: c.join()
    finally:
        stop_server(server)

def run_scenario_4_mixed_watchers():
    # 4. 1 client watching 2 items (1 cargo 1 container)
    print(f"\n{'='*60}\nSCENARIO 4: Mixed Watching (1 Cargo, 1 Container)\n{'='*60}")
    
    server = start_server()
    try:
        setup = [
            "CREATE_ITEM S1 R1 A1 O1",
            "CREATE_CONTAINER CONT1 Truck Truck 0 0",
            3.0,
            "COMPLETE CI00000001", # Trigger Item Notification
            1.0,
            "SETLOC CONT1 50 50",  # Trigger Container Notification
            1.0,
            "QUIT"
        ]

        # One client sends two watch commands
        w1 = [1.5, "WATCH CI00000001", "WATCH_CONTAINER CONT1", 10.0]

        clients = [
            DemoClient("Updater", "UPDATER", setup),
            DemoClient("MixedWatcher", "WATCH_A", w1),
        ]
        for c in clients: c.start()
        for c in clients: c.join()
    finally:
        stop_server(server)

def run_scenario_5_save():
    # 5. Save and Persistence check
    print(f"\n{'='*60}\nSCENARIO 5: Save & Persistence\n{'='*60}")
    
    # Create and Save
    server = start_server()
    try:
        setup = [
            "CREATE_ITEM SavedItem Recip Addr Owner",
            "SAVE",
            1.0, "QUIT"
        ]
        c = DemoClient("Saver", "UPDATER", setup)
        c.start()
        c.join()
    finally:
        print("--- Stopping Server (Keeping State) ---")
        server.kill()
        server.wait()

    time.sleep(1)

    # Restart and Verify
    print("--- Restarting Server ---")
    server = subprocess.Popen([sys.executable, 'server.py'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(1)

    try:
        verify = ["LIST_ITEMS", 1.0, "QUIT"]
        c = DemoClient("Verifier", "VERIFIER", verify)
        c.start()
        c.join()
    finally:
        # Cleanup
        stop_server(server)

def run_scenario_6_wait_events():
    # 6. Synchronous Waiting (WAIT_EVENTS)
    print(f"\n{'='*60}\nSCENARIO 6: Synchronous Waiting (WAIT_EVENTS)\n{'='*60}")
    
    server = start_server()
    try:
        setup = [
            "CREATE_ITEM S1 R1 A1 O1", # CI...01
            2.0,
            "QUIT"
        ]
        
        # Client A watches and then WAITS. 
        # The WAIT_EVENTS command should block until an event occurs or timeout.
        # We simulate the block by having Client B update late.
        watch_wait = [
            1.0, 
            "WATCH CI00000001", 
            0.5,
            "WAIT_EVENTS", # This should hang here until Client B triggers it
            2.5,
            "QUIT"
        ]
        
        # Client B updates the item after Client A has started waiting
        updater = [
            3.0, 
            "COMPLETE CI00000001", 
            "QUIT"
        ]

        clients = [
            DemoClient("Setup", "UPDATER", setup),
            DemoClient("Waiter", "WATCH_A", watch_wait),
            DemoClient("Trigger", "UPDATER2", updater),
        ]
        
        for c in clients: c.start()
        for c in clients: c.join()
    finally:
        stop_server(server)

def run_scenario_7_poll_vs_push():
    # 7. Polling vs. Pushing
    print(f"\n{'='*60}\nSCENARIO 7: Polling vs. Pushing\n{'='*60}")
    
    server = start_server()
    try:
        setup = [
            "CREATE_ITEM S1 R1 A1 O1", # CI...01
            1.0,
            "QUIT"
        ]
        
        # Client A (Watcher) - Passive, gets notifications
        watcher = [
            1.5,
            "WATCH CI00000001",
            5.0, # Just sit and wait for notifications
            "QUIT"
        ]
        
        # Client B (Poller) - Active, asks for status repeatedly
        poller = [
            1.5,
            "STATUS CI00000001",
            1.0,
            "STATUS CI00000001",
            1.0,
            "STATUS CI00000001", 
            1.0,
            "STATUS CI00000001",
            "QUIT"
        ]
        
        # Updater moves item in the middle of polling
        updater = [
            3.5,
            "COMPLETE CI00000001",
            "QUIT"
        ]

        clients = [
            DemoClient("Setup", "UPDATER", setup),
            DemoClient("Watcher", "WATCH_A", watcher),
            DemoClient("Poller", "POLLER", poller),
            DemoClient("Updater", "UPDATER2", updater),
        ]
        
        for c in clients: c.start()
        for c in clients: c.join()
    finally:
        stop_server(server)

def run_scenario_8_disconnection():
    # 8. Client Disconnection Handling
    print(f"\n{'='*60}\nSCENARIO 8: Client Disconnection Handling\n{'='*60}")
    
    server = start_server()
    try:
        setup = [
            "CREATE_ITEM S1 R1 A1 O1", # CI...01
            "CREATE_ITEM S2 R2 A2 O2", # CI...02
            1.0,
            "QUIT"
        ]
        
        # Client A watches then abruptly disconnects
        # We use a special command "__CLOSE_SOCKET__" handled in DemoClient
        dropper = [
            1.5,
            "WATCH CI00000001",
            1.0,
            "__CLOSE_SOCKET__" # Abrupt disconnect
        ]
        
        # Client B updates the item after A has disconnected.
        # This verifies the server doesn't crash trying to notify A.
        updater = [
            3.5,
            "COMPLETE CI00000001", # Should trigger update logic on server
            "COMPLETE CI00000002", # Control check
            "QUIT"
        ]

        clients = [
            DemoClient("Setup", "UPDATER", setup),
            DemoClient("Dropper", "WATCH_A", dropper),
            DemoClient("Updater", "UPDATER2", updater),
        ]
        
        for c in clients: c.start()
        for c in clients: c.join()
    finally:
        stop_server(server)

def main():
    run_scenario_1_concurrency()
    run_scenario_2_item_watchers()
    run_scenario_3_container_watchers()
    run_scenario_4_mixed_watchers()
    run_scenario_5_save()
    run_scenario_6_wait_events()
    run_scenario_7_poll_vs_push()
    run_scenario_8_disconnection()

if __name__ == "__main__":
    main()