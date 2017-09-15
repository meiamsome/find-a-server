import codecs
import socket

from minecraft.types import short
from minecraft.types.exceptions import ProtocolException, \
    UnimplementedException, IncorrectProtocolException


def query(proto, addr, timeout):
    conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    conn.settimeout(timeout)
    conn.connect(addr)
    try:
        packet = "\xFE\x01"
        packet += "\xFA"
        mcstr = "MC|PingHost"
        packet += short.to_stream(len(mcstr))
        packet += codecs.encode(mcstr, 'utf-16-be')
        host = str(addr[0])
        packet += short.to_stream(len(host)*2 + 7)
        packet += "\x4E"  # Current proto version
        packet += short.to_stream(len(host))
        packet += codecs.encode(host, 'utf-16-be')
        packet += "\x00\x00" + short.to_stream(int(addr[1]))
        send_message(conn, packet)
        data_buffer = []
        while True:
            data = conn.recv(4096)
            data_buffer += data
            if not data:
                break
        if not data_buffer:
            raise ProtocolException("Server responded incorrectly.")
        if data_buffer[0] != '\xFF':
            raise ProtocolException("Server responded incorrectly.")
        try:
            datastr = codecs.decode("".join(data_buffer[3:]), 'utf-16-be')
        except ValueError:
            raise ProtocolException("Could not decode server info")
        data = datastr.split("\0")
        if len(data) != 6:
            raise ProtocolException("Could not decode server info, weird data")
        if int(data[1]) == 127:
            raise IncorrectProtocolException()
        return {
            'version': {
                'name': data[2],
                'protocol': -int(data[1]),
            },
            'players': {
                'max': int(data[5]),
                'online': int(data[4]),
            },
            'description': {
                'text': data[3]
            },
        }
    finally:
        conn.close()


def connect(proto, addr, timeout, username, debug=False):
    raise UnimplementedException(
        "Online-mode servers are not programmed in yet."
    )


def send_message(conn, message):
    start = size = len(message)
    while size:
        size -= conn.send(message[start-size:])
