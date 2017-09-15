import socket
import struct


class MinecraftQuery:
    MAGIC_PREFIX = '\xFE\xFD'
    PACKET_TYPE_CHALLENGE = 9
    PACKET_TYPE_QUERY = 0
    HUMAN_READABLE_NAMES = {
        "game_id": "Game Name",
        "gametype": "Game Type",
        "motd": "Message of the Day",
        "hostname": "Server Address",
        "hostport": "Server Port",
        "map": "Main World Name",
        "maxplayers": "Maximum Players",
        "numplayers": "Players Online",
        "players": "List of Players",
        "plugins": "List of Plugins",
        "raw_plugins": "Raw Plugin Info",
        "software": "Server Software",
        "version": "Game Version",
    }

    def __init__(self, host, port, timeout=10, query_id=0, retries=2):
        self.addr = (host, port)
        self.query_id = query_id
        self.query_id_packed = struct.pack('>l', query_id)
        self.challenge = None
        self.challenge_packed = None
        self.retries = 0
        self.max_retries = retries

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.settimeout(timeout)

    def send_raw(self, data):
        self.socket.sendto(self.MAGIC_PREFIX + data, self.addr)

    def send_packet(self, packet_type, data=''):
        self.send_raw(
            struct.pack('>B', packet_type) +
            self.query_id_packed +
            self.challenge_packed +
            data
        )

    def read_packet(self):
        buff = self.socket.recvfrom(4096)[0]
        packet_type = struct.unpack('>B', buff[0])[0]
        return_id = struct.unpack('>l', buff[1:5])[0]
        return packet_type, return_id, buff[5:]

    def handshake(self, bypass_retries=False):
        self.send_packet(self.PACKET_TYPE_CHALLENGE)

        try:
            _, _, buff = self.read_packet()
        except:
            if not bypass_retries:
                self.retries += 1

            if self.retries < self.max_retries:
                self.handshake(bypass_retries=bypass_retries)
                return
            else:
                raise

        self.challenge = int(buff[:-1])
        self.challenge_packed = struct.pack('>l', self.challenge)

    def get_status(self):
        if not hasattr(self, 'challenge'):
            self.handshake()

        self.send_packet(self.PACKET_TYPE_QUERY)

        try:
            _, _, buff = self.read_packet()
        except:
            self.handshake()
            return self.get_status()

        data = {}

        (
            data['motd'],
            data['gametype'],
            data['map'],
            data['numplayers'],
            data['maxplayers'],
            buff
        ) = buff.split('\x00', 5)
        data['hostport'] = struct.unpack('<h', buff[:2])[0]
        buff = buff[2:]
        data['hostname'] = buff[:-1]

        for key in ('numplayers', 'maxplayers'):
            try:
                data[key] = int(data[key])
            except:
                pass

        return data

    def get_rules(self):
        if not hasattr(self, 'challenge'):
            self.handshake()

        self.send_packet(self.PACKET_TYPE_QUERY, self.query_id_packed)

        try:
            _, _, buff = self.read_packet()
        except:
            self.retries += 1
            if self.retries < self.max_retries:
                self.handshake(bypass_retries=True)
                return self.get_rules()
            else:
                raise

        data = {}

        # splitnum + 2 ints
        buff = buff[11:]
        items, players = buff.split('\x00\x00\x01player_\x00\x00')

        if items[:8] == 'hostname':
            items = 'motd' + items[8:]

        items = items.split('\x00')
        data = dict(zip(items[::2], items[1::2]))

        players = players[:-2]

        if players:
            data['players'] = players.split('\x00')
        else:
            data['players'] = []

        for key in ('numplayers', 'maxplayers', 'hostport'):
            try:
                data[key] = int(data[key])
            except ValueError:
                pass

        data['raw_plugins'] = data['plugins']
        data['software'], data['plugins'] = parse_plugins(
            data['raw_plugins']
        )

        return data


def parse_plugins(raw):
    parts = raw.split(':', 1)
    server = parts[0].strip()
    plugins = []

    if len(parts) == 2:
        plugins = parts[1].split(';')
        plugins = [p.strip() for p in plugins]

    return server, plugins
