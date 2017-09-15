import json
import socket

from minecraft.types import short, varint, string
from minecraft.types.exceptions import ProtocolException, \
    DisconnectException, UnimplementedException


def query(proto, addr, timeout):
    conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    conn.settimeout(timeout)
    conn.connect(addr)
    try:
        send_message(conn, prepare_handshake(addr, proto, 1))
        send_message(conn, string.to_stream("\x00"))
        data_buffer = []
        while True:
            pack = get_packet(conn, data_buffer)
            if pack is None:
                raise ProtocolException(
                    "Connection closed while waiting for query.")
            pid, start = varint.from_stream(pack)
            if pid == 0:
                query_result = string.from_stream(pack[start:])
                return json.loads("".join(query_result[0]), strict=False)
            else:
                raise ProtocolException(
                    "Unknown packet ID %x received while querying." % pid)
    finally:
        conn.close()


def connect(proto, addr, timeout, username, debug=False):
    conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    conn.settimeout(timeout)
    conn.connect(addr)
    send_message(conn, prepare_handshake(addr, proto, 2))
    send_message(conn, string.to_stream(
        "\x00" + string.to_stream(str(username))))
    data_buffer = []
    logged_in = False
    while True:
        pack = get_packet(conn, data_buffer)
        if pack is None:
            return
        pid, start = varint.from_stream(pack)
        if debug:
            print("Packed ID %i" % pid)
        if pid == 0:
            # Disconnect, raise reason
            raise DisconnectException(string.from_stream(pack[start:])[0])
        elif pid == 1:
            raise UnimplementedException(
                "Online-mode servers are not programmed in yet.")
            # logged_in = True
            # server_id, startinc = string.from_stream(pack[start:])
            # start += startinc
            # print("Server_id: '%s'" % server_id)
            # len, startinc = short.from_stream(pack[start:])
            # start += startinc
            # pub_key = pack[start: start + len]
            # start += len
            # len, startinc = short.from_stream(pack[start:])
            # start += startinc
            # token = pack[start: start + len]
            # start += len
            # print("Public key:")
            # print(["%x" % ord(x) for x in pub_key])
            # print(",".join(pub_key))
            # print("Verify Token:")
            # print(token)
        elif pid == 2:
            if not logged_in:
                conn.close()
                return
        elif pid == 3:
            pass
        else:
            raise ProtocolException(
                "Server replied in an unexpected manner (Packet ID %i)" % pid)


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
        data_buffer[:stop + length] = []
        return pack


def prepare_handshake(addr, proto, qtype):
    message = "\x00"
    # Protocol Version
    message += varint.to_stream(proto)
    # Host Name
    message += str(string.to_stream(addr[0]))
    # Port
    message += short.to_stream(addr[1])
    # Request type
    message += varint.to_stream(qtype)
    return string.to_stream(message)


def send_message(conn, message):
    start = size = len(message)
    while size:
        size -= conn.send(message[start - size:])
