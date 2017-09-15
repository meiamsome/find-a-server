import socket
from time import sleep

from minecraft.client.protocol import old_proto_1, new_protocol_base
from minecraft.types.exceptions import UnimplementedException, \
    ProtocolException

protocol_versions = [
    (new_protocol_base, 47),
    (new_protocol_base, 5),
    (old_proto_1, None),
]


def query(address, timeout=10, protocol_number=0, cascade=True):
    try:
        return protocol_versions[protocol_number][0].query(
            protocol_versions[protocol_number][1],
            address,
            timeout
        )
    except (socket.timeout, ProtocolException, socket.error):
        if not cascade or protocol_number == len(protocol_versions) - 1:
            raise
        sleep(5)
        return query(address, timeout, protocol_number + 1)


def check_online_mode(address, username, timeout=10,
                      protocol_number=None, debug=False):
    if protocol_number is None:
        protocol_number = query(address, timeout)['version']['protocol']
    try:
        proto = int(protocol_number)
    except ValueError:
        raise UnimplementedException("Cannot check online mode.")
    try:
        if proto > 0:
            new_protocol_base.connect(proto, address, timeout,
                                      username, debug=debug)
        else:
            return None
    except UnimplementedException:
        return True
    return False


def cli():
    server = raw_input("What server would you like to connect to?\n")
    print("Querying server for info.")
    q = query((server, 25565), 10)
    protocol = int(q['version']['protocol'])
    print(q)
    print("Server is running protocol %s " % protocol)
    try:
        print("%i/%i" % (int(q['players']['online']), int(q['players']['max'])))
    except Exception as e:
        print(e)
    print("Online mode check:")
    print(check_online_mode((server, 25565), 'FindAServer', protocol_number=q['version']['protocol']))


if __name__ == "__main__":
    cli()
