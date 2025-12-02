from threading import Thread, RLock, Condition
from socket import socket, AF_INET, SOCK_STREAM
from itertools import count
import sys
import json
import time
import os

# import library classes
from cargo_item import CargoDirectory, CargoItem
from container import Container
from tracker import Tracker

# Shared model
_model_lock = RLock()
_directory = CargoDirectory()
_containers = {}
tracker_sequence = count(1)
STATE_FILE = 'server_state.json'


def save_state(path=STATE_FILE):
    with _model_lock:
        items = [json.loads(payload) for _, payload in _directory.list()]
        containers = [json.loads(cont.get()) for cont in _containers.values()]
    data = {
        'items': items,
        'containers': containers,
    }
    try:
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump(data, handle, indent=2)
    except OSError as exc:
        print(f'WARN: failed to save state: {exc}')


def load_state(path=STATE_FILE):
    if not os.path.exists(path):
        return
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        print(f'WARN: failed to load state: {exc}')
        return

    items_data = data.get('items', [])
    containers_data = data.get('containers', [])

    new_directory = CargoDirectory()
    new_directory._items.clear()
    new_directory._attachments.clear()
    new_containers = {}

    with _model_lock:
        # build containers first
        for cont_payload in containers_data:
            try:
                cont = Container(
                    cid=cont_payload['cid'],
                    description=cont_payload['description'],
                    type=cont_payload['type'],
                    loc=tuple(cont_payload['loc']),
                )
            except Exception:
                continue
            cont._items.clear()
            new_containers[cont.cid] = cont

        max_id = 0
        for item_payload in items_data:
            try:
                item = CargoItem(
                    sendernam=item_payload['sendernam'],
                    recipnam=item_payload['recipnam'],
                    recipaddr=item_payload['recipaddr'],
                    owner=item_payload['owner'],
                )
            except Exception:
                continue
            # overwrite auto id with saved id
            auto_id = item.trackingId()
            new_directory._items.pop(auto_id, None)
            saved_id = item_payload.get('id', auto_id)
            item._tracking_id = saved_id
            item.state = item_payload.get('state', item.state)
            item._deleted = item_payload.get('deleted', False)
            item._container = None
            item._container_id = None
            item._trackers = set()
            new_directory._items[saved_id] = item

            try:
                idx = int(saved_id[2:]) if saved_id.startswith('CI') else 0
            except ValueError:
                idx = 0
            max_id = max(max_id, idx)

        # restore container assignments
        for item_payload in items_data:
            item_id = item_payload.get('id')
            container_id = item_payload.get('container')
            if not item_id or not container_id:
                continue
            item = new_directory._items.get(item_id)
            container = new_containers.get(container_id)
            if item is None or container is None:
                continue
            container._items.add(item)
            item._container = container
            item._container_id = container_id

        CargoItem._id_sequence = count(max_id + 1)

        global _directory, _containers
        _directory = new_directory
        _containers = new_containers


class Session(Thread):
    def __init__(self, sock):
        super().__init__()
        self.socket = sock
        self.cond = Condition()
        self.events = []
        self.username = 'guest'
        self.tracker = Tracker(
            tid=f"TRK{next(tracker_sequence):06d}",
            description="session tracker",
            owner=self.username,
            on_update=self._on_tracker_update,
        )
        self._running = True
        self._buffer = ''
        self.pending_events = 0
        self._event_counter = 0

    def run(self):
        # start notification agent
        self.agent = Thread(target=notificationagent, args=(self,))
        self.agent.daemon = True
        self.agent.start()

        try:
            while self._running:
                data = self.socket.recv(1024)
                if data == b'' or not data:
                    break
                self._buffer += data.decode('utf-8', errors='ignore')
                # handle multiple lines in the buffer
                while '\n' in self._buffer:
                    line, self._buffer = self._buffer.split('\n', 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        resp, cont = self.handle(line)
                    except Exception as e:
                        resp = 'ERR ' + str(e)
                        cont = True
                    # send back response line
                    try:
                        self.socket.sendall((resp + '\n').encode('utf-8'))
                    except Exception:
                        self._running = False
                        break
                    if not cont:
                        self._running = False
                        break
        finally:
            self.close()

    def handle(self, line):
        parts = line.split()
        cmd = parts[0].upper()
        args = parts[1:]

        if cmd == 'HELP':
            return ('Commands: HELP, USER <name>, CREATE_ITEM <s> <r> <a> <owner>, CREATE_CONTAINER <cid> <desc> <type> <lon> <lat>, LIST_ITEMS, LIST_CONTAINERS, WATCH <item>, WATCH_CONTAINER <cid>, LOAD <item> <cid>, UNLOAD <item>, COMPLETE <item>, SETLOC <cid> <lon> <lat>, STATUS <item>, WAIT_EVENTS, SAVE, QUIT', True)
        if cmd == 'USER':
            if len(args) != 1:
                raise ValueError('Usage: USER <name>')
            self.username = args[0]
            try:
                self.tracker.update(owner=self.username)
            except Exception:
                pass
            return (f'OK hello {self.username}', True)
        if cmd == 'CREATE_ITEM':
            if len(args) < 4:
                raise ValueError('Usage: CREATE_ITEM <sender> <recipient> <address> <owner>')
            with _model_lock:
                item_id = _directory.create(sendernam=args[0], recipnam=args[1], recipaddr=args[2], owner=args[3])
            return ('OK ' + item_id, True)
        if cmd == 'CREATE_CONTAINER':
            if len(args) < 5:
                raise ValueError('Usage: CREATE_CONTAINER <cid> <desc> <type> <lon> <lat>')
            with _model_lock:
                cid = args[0]
                if cid in _containers:
                    raise RuntimeError('container exists')
                cont = Container(cid=cid, description=args[1], type=args[2], loc=(float(args[3]), float(args[4])))
                _containers[cid] = cont
            return ('OK ' + cid, True)
        if cmd == 'LIST_ITEMS':
            with _model_lock:
                items = _directory.list()
            return ('OK ' + json.dumps([p for _, p in items]), True)
        if cmd == 'LIST_CONTAINERS':
            with _model_lock:
                data = [json.loads(c.get()) for c in _containers.values()]
            return ('OK ' + json.dumps(data), True)
        if cmd == 'WATCH':
            if len(args) != 1:
                raise ValueError('Usage: WATCH <item_id>')
            item_id = args[0]
            with _model_lock:
                item = _directory._items.get(item_id)
                if item is None:
                    raise KeyError('Unknown item')
                self.tracker.addItem([item])
            return (f'OK watching {item_id}', True)
        if cmd == 'WATCH_CONTAINER':
            if len(args) != 1:
                raise ValueError('Usage: WATCH_CONTAINER <cid>')
            cid = args[0]
            with _model_lock:
                cont = _containers.get(cid)
                if cont is None:
                    raise KeyError('Unknown container')
                self.tracker.addContainer([cont])
            return (f'OK watching container {cid}', True)
        if cmd == 'LOAD':
            if len(args) != 2:
                raise ValueError('Usage: LOAD <item> <cid>')
            item_id, cid = args[0], args[1]
            with _model_lock:
                item = _directory._items.get(item_id)
                cont = _containers.get(cid)
                if item is None or cont is None:
                    raise KeyError('Unknown item or container')
                current = item.getContainer()
                if current and current != cid:
                    raise RuntimeError(f'Item already in container {current}')
                if current == cid:
                    return (f'OK {item_id} already in {cid}', True)
                cont.load([item])
            return (f'OK loaded {item_id} into {cid}', True)
        if cmd == 'SETLOC':
            if len(args) != 3:
                raise ValueError('Usage: SETLOC <cid> <lon> <lat>')
            cid = args[0]
            with _model_lock:
                cont = _containers.get(cid)
                if cont is None:
                    raise KeyError('Unknown container')
                cont.setlocation(float(args[1]), float(args[2]))
            return (f'OK moved {cid}', True)
        if cmd == 'UNLOAD':
            if len(args) != 1:
                raise ValueError('Usage: UNLOAD <item_id>')
            item_id = args[0]
            with _model_lock:
                item = _directory._items.get(item_id)
                if item is None:
                    raise KeyError('Unknown item')
                cont = getattr(item, '_container', None)
                if cont is None:
                    raise RuntimeError('Item not in a container')
                # call unload on the container
                try:
                    cont.unload([item])
                except Exception as e:
                    raise RuntimeError(f'Unload failed: {e}')
            return (f'OK unloaded {item_id}', True)
        if cmd == 'COMPLETE':
            if len(args) != 1:
                raise ValueError('Usage: COMPLETE <item_id>')
            item_id = args[0]
            with _model_lock:
                item = _directory._items.get(item_id)
                if item is None:
                    raise KeyError('Unknown item')
                if item.state == 'complete':
                    return (f'OK {item_id} already complete', True)
                try:
                    item.complete()
                except Exception as e:
                    raise RuntimeError(f'Complete failed: {e}')
            return (f'OK completed {item_id}', True)
        if cmd == 'STATUS':
            if len(args) != 1:
                raise ValueError('Usage: STATUS <item_id>')
            with _model_lock:
                item = _directory._items.get(args[0])
                if item is None:
                    raise KeyError('Unknown item')
                return ('OK ' + item.get(), True)
        if cmd == 'WAIT_EVENTS':
            timeout = 5.0
            end = time.time() + timeout
            with self.cond:
                start_counter = self._event_counter
                while self._event_counter == start_counter and self._running:
                    remaining = end - time.time()
                    if remaining <= 0:
                        break
                    self.cond.wait(timeout=remaining)
                event_observed = self._event_counter != start_counter
            if event_observed:
                return ('OK event available', True)
            return ('OK no pending events', True)
        if cmd == 'SAVE':
            save_state()
            return ('OK saved', True)
        if cmd == 'QUIT':
            return ('OK bye', False)
        raise ValueError('Unknown command')

    def _on_tracker_update(self, tracker_obj, updated_object, obj_id):
        brief = {
            'when': time.time(),
            'obj': ('generic', None, None),
        }
        if isinstance(updated_object, CargoItem):
            brief['obj'] = ('cargo', obj_id, getattr(updated_object, 'state', None))
        elif isinstance(updated_object, Container):
            brief['obj'] = ('container', obj_id, getattr(updated_object, 'loc', None))
        elif isinstance(updated_object, Tracker):
            brief['obj'] = ('tracker', tracker_obj.tid, None)

        with self.cond:
            self._event_counter += 1
            self.events.append(brief)
            self.pending_events += 1
            self.cond.notify_all()

    def close(self):
        # unregister watchers
        with _model_lock:
            try:
                self.tracker.delete()
            except Exception:
                pass
        try:
            self.socket.close()
        except Exception:
            pass
        # stop agent
        self._running = False
        with self.cond:
            self.cond.notify_all()


def notificationagent(session):
    while True:
        with session.cond:
            while not session.events and session._running:
                session.cond.wait()
            if not session._running and not session.events:
                break
            ev = session.events.pop(0)
        try:
            session.socket.sendall(('EVENT ' + json.dumps(ev) + '\n').encode('utf-8'))
        except Exception:
            session._running = False
            break
        finally:
            with session.cond:
                session.pending_events = max(0, session.pending_events - 1)
                if session.pending_events == 0:
                    session.cond.notify_all()


if __name__ == '__main__':
    port = 5000
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print('port must be integer, using 5000')
    load_state()
    serversocket = socket(AF_INET, SOCK_STREAM)
    serversocket.bind(('', port))
    serversocket.listen(10)
    print('server2 listening on port', port)

    try:
        while True:
            ns, peer = serversocket.accept()
            s = Session(ns)
            s.start()
    finally:
        serversocket.close()
        save_state()
