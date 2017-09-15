from minecraft.server.protocol import proto5, proto19
from minecraft.types.exceptions import UnsupportedProtocolException


def handle(server, conn, addr, handshake, data_buffer):
    # handshake[0] is protocol version
    if handshake[0] >= 19:
        proto19.handle(server, conn, addr, handshake, data_buffer)
    elif handshake[0] > 0:
        proto5.handle(server, conn, addr, handshake, data_buffer)
    else:
        conn.close()
        # Unknown Proto Version
        raise UnsupportedProtocolException(
            "Unsupported Protocol Version." + str(handshake[0])
        )
