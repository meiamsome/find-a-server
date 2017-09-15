import os
import socket
import time
from Crypto import Random
from Crypto.PublicKey import RSA

from minecraft.server.protocol import handler
from minecraft.types import varint, string
from minecraft.types.exceptions import ProtocolException


def run_server(addr):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    retries = 0
    while True:
        try:
            sock.bind(addr)
            break
        except socket.error, val:
            if val.errno != 98:
                raise
            # print("Failed to bind. Retrying")
            if retries > 5:
                raise
            retries += 1
            time.sleep(0.5)
    # print("Bound successfully")
    sock.settimeout(60)
    sock.listen(20)

    server = {}
    # print("Generating key pair.")
    server['key'] = RSA.generate(1024)
    # print("Key pair generated.")

    while True:
        try:
            conn, addr = sock.accept()
        except socket.timeout:
            pass
        else:
            if not os.fork():
                Random.atfork()
                client_handshake(server, conn, addr)
                return
        pid = 1
        try:
            while pid != 0:
                pid, stat, use = os.wait3(os.WNOHANG)
        except OSError:
            pass


def client_handshake(server, conn, addr):
    try:
        handshake = None
        data_buffer = []
        while True:
            pack = get_packet(conn, data_buffer)
            if pack is None:
                print("Disconnect.")
                return
            if ord(pack[0]) != 0:
                # No handshake, connection rejected.
                conn.close()
            handshake = read_handshake(pack[1:])
            handler.handle(server, conn, addr, handshake, data_buffer)
    finally:
        conn.close()


def read_handshake(pack):
    stop = 0
    client_info = []
    # Proto Vers
    info, stopi = varint.from_stream(pack[stop:])
    stop += stopi
    client_info.append(info)
    # Hostname
    info, stopi = string.from_stream(pack[stop:])
    stop += stopi
    client_info.append(info)
    # Port
    client_info.append(((ord(pack[stop]) << 8) + ord(pack[stop + 1])))
    stop += 2
    # Next State
    info, stop = varint.from_stream(pack[stop:])
    client_info.append(info)
    return tuple(client_info)


def send_message(conn, message):
    start = size = len(message)
    while size:
        size -= conn.send(message[start-size:])


def get_packet(conn, data_buffer):
    while True:
        try:
            length, stop = varint.from_stream(data_buffer)
        except ProtocolException:
            data = conn.recv(4096)
            if not data:
                conn.close()
                return None
            data_buffer += data
            continue
        while len(data_buffer) < stop + length:
            data = conn.recv(4096)
            if not data:
                conn.close()
                return None
            data_buffer += data
        pack = data_buffer[stop:stop + length]
        data_buffer[:stop+length] = []
        return pack


if __name__ == "__main__":
    run_server((socket.gethostname(), 25565))
