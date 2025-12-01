"""Tiny interactive TCP client for the cargo tracking server.

Usage:
    python client.py [host] [port]

Run the server in one terminal:
    python server.py 5000

Open another terminal and run this client to interact:
    python client.py localhost 5000

Type commands (e.g. HELP, PING, USER alice, CREATE_ITEM A B C Owner, LIST_ITEMS, WATCH <id>)
"""

import sys
import socket
import threading

HOST = 'localhost'
PORT = 5000

if len(sys.argv) > 1:
    HOST = sys.argv[1]
if len(sys.argv) > 2:
    try:
        PORT = int(sys.argv[2])
    except ValueError:
        print('Invalid port, using 5000')
        PORT = 5000

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    sock.connect((HOST, PORT))
except Exception as e:
    print('Failed to connect:', e)
    sys.exit(1)

stop_event = threading.Event()


def receiver():
    while not stop_event.is_set():
        try:
            data = sock.recv(4096)
            if not data:
                print('\nConnection closed by server')
                stop_event.set()
                break
            # print raw bytes decoded
            print('\n' + data.decode('utf-8', errors='ignore'), end='')
        except Exception:
            stop_event.set()
            break


recv_thread = threading.Thread(target=receiver, daemon=True)
recv_thread.start()

try:
    while not stop_event.is_set():
        line = input()
        if not line:
            continue
        try:
            sock.sendall((line.strip() + '\n').encode('utf-8'))
        except Exception:
            print('Failed to send, closing')
            stop_event.set()
            break
except (KeyboardInterrupt, EOFError):
    print('\nExiting client...')
finally:
    stop_event.set()
    try:
        sock.close()
    except Exception:
        pass
