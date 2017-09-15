import itertools
from multiprocessing import Process, Queue
import Queue as NormalQueue
import socket
import struct

# Status codes
START = 0
HANDSHAKE = 1
FULL_QUERY = 2


class AsyncQuery(object):
    def __init__(self, output_queue=Queue()):
        self.output_queue = output_queue
        self.my_connection = None
        self.my_process = None
        self.my_queue = None
        self.id_holder = 0
        self.id_to_data = {}
        self.retries = 5

    def __enter__(self):
        self.my_queue = Queue()
        self.my_process = Process(None, self._handle)
        self.my_process.start()
        return self

    def __exit__(self, type, value, traceback):
        try:
            self.my_process.terminate()
            self.my_process.join()
        except AttributeError:
            pass
        try:
            self.my_queue.close()
        except AttributeError:
            pass

    def set_retries(self, retries):
        self.retries = retries

    def query(self, address, queue_args=tuple()):
        self.my_queue.put_nowait({
            'address': address,
            'queue_args': queue_args
        })

    def _handle(self):
        self.my_connection = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.my_connection.settimeout(0.001)
        while True:
            self._accept_servers()
            self._handle_socket()

    def _accept_servers(self):
        try:
            while True:
                self._add_server(self.my_queue.get_nowait())
        except NormalQueue.Empty:
            pass

    def _add_server(self, data):
        data['id'] = self.id_holder
        data['status'] = START
        self.id_to_data[self.id_holder] = data
        self.id_holder += 1
        self._send_handshake(data)

    def _remove_server(self, server_id):
        del self.id_to_data[server_id]

    def _send_handshake(self, data):
        handshake = "\xFE\xFD\x09" + struct.pack(">l", data['id'])
        handshake += struct.pack(">l", 0)
        self.id_to_data[data['id']]['status'] = HANDSHAKE
        try:
            self.my_connection.sendto(handshake, data['address'])
        except Exception as e:
            data['exception_callback'](e)

    def _handle_socket(self):
        while True:
            try:
                received = self.my_connection.recvfrom(4096)
            except socket.timeout:
                break
            else:
                packet = AsyncQuery._read_packet(received[0])
                packet_type, server_id, packet_buffer = packet
                if self._handle_packet(server_id, packet_type, packet_buffer):
                    self._remove_server(server_id)

    def _handle_packet(self, server_id, packet_type, packet):
        try:
            data = self.id_to_data[server_id]
            if data['status'] == 1 and packet_type == 9:
                self._send_query_request(server_id, packet)
            elif data['status'] == 2 and packet_type == 0:
                self._handle_full_query(server_id, packet)
                return True
            return False
        except KeyboardInterrupt:
            raise
        except Exception:
            return False

    def _send_query_request(self, server_id, packet):
        data = self.id_to_data[server_id]
        challenge_id = int(packet[:-1])
        query = "\xFE\xFD\x00" + struct.pack(">l", server_id)
        query += struct.pack(">l", challenge_id) + struct.pack(">l", 0)
        self.my_connection.sendto(query, data['address'])
        data['status'] = FULL_QUERY

    def _handle_full_query(self, server_id, packet):
        data = self.id_to_data[server_id]
        # Drop first 11 bytes (Don't care)
        packet = packet[11:]
        info = packet.split("\x00\x01player_\x00\x00")
        players = info[1][:-2]
        if players:
            players = players.split("\x00")
            self.output_queue.put(list(itertools.chain(
                data['queue_args'], (players, )
            )))

    # Helper method to open the query packet
    @staticmethod
    def _read_packet(packet):
        return (
            struct.unpack('>B', packet[0])[0],
            struct.unpack('>l', packet[1:5])[0],
            packet[5:]
        )


# sys.modules[__name__] = AsyncQuery
