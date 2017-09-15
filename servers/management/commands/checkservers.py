from contextlib import contextmanager
from datetime import datetime, timedelta
import errno
from multiprocessing import Queue, Process
import os
import Queue as NormalQueue
import socket
import time

from django.core.management.base import BaseCommand
try:
    from django.db.transaction import atomic
except ImportError:
    from django.db.transaction import commit_on_success as atomic
from django.db.utils import OperationalError
from django.utils.timezone import utc

from servers import user_requester
from servers.models import Server, UpTime, PlayTime
from servers.helpers import total_seconds
from minecraft.client import fake_client, async_query
from minecraft.types.exceptions import DisconnectException, \
    IncorrectProtocolException

# TODO: Add a lot of documentation to this


class Enum(set):
    def __getattr__(self, name):
        if name in self:
            return name
        raise AttributeError


WORK = Enum(['BASIC_QUERY'])
QUEUES = Enum(['WORK', 'LESS_IMPORTANT_WORK', 'DEEP_QUERY'])

ONLINE_MODE_EXPIRY = timedelta(hours=3)
PLAYTIME_EXPIRY = timedelta(minutes=10)
PLAYER_EXPIRY = timedelta(hours=6)
SERVER_OFFLINE_RESCAN_TIME = [
    timedelta(seconds=120),
    timedelta(seconds=600),
    timedelta(minutes=30),
    timedelta(hours=1)
]
SERVER_ONLINE_RESCAN_TIME = timedelta(seconds=30)


@contextmanager
def get_lock(process_name):
    lock_socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    lock_socket.bind(process_name)
    try:
        yield lock_socket
    finally:
        lock_socket.close()
        os.unlink(process_name)


@contextmanager
def open_pool(count, function, args=(), kwargs=None):
    pool = {
        'function': function,
        'args': args,
        'kwargs': kwargs if kwargs is not None else {},
        'processes': []
    }
    resize_pool(pool, count)
    try:
        yield pool
    finally:
        for process in pool['processes']:
            process.terminate()
            process.join()


def resize_pool(pool, new_count):
    to_add = new_count - len(pool['processes'])
    if to_add <= 0:  # Not supported yet
        return
    for _ in xrange(to_add):
        process = Process(None, pool['function'], args=pool['args'],
                          kwargs=pool['kwargs'])
        process.start()
        pool['processes'].append(process)


def revive_pool(pool):
    to_remove = []
    for process in pool['processes']:
        if not process.is_alive():
            process.join()
            to_remove.append(process)
    for process in to_remove:
        pool['processes'].remove(process)
        process = Process(None, pool['function'], args=pool['args'],
                          kwargs=pool['kwargs'])
        process.start()
        pool['processes'].append(process)
    if to_remove:
        print("Revivied " + str(len(to_remove)) + " threads.")


@contextmanager
def open_queue():
    queue = Queue()
    try:
        yield queue
    finally:
        queue.close()


class Command(BaseCommand):
    def __init__(self):
        super(Command, self).__init__()
        self.work_queue = None
        self.less_important_work_queue = None
        self.time_delay_queue = None
        self.save_queue = None
        self.deep_query_handler = None
        self.deep_query_queue = None
        self.deep_query_output = None
        self.player_request_queue = None
        self.player_response_queue = None
        # Stores the maximum server ID, used to fetch new servers
        self.max_server_id = 0
        # Stores the maximum playtime ID, used to ID them.
        # (Bad idea, but it is in another thread :/)
        self.next_playtime_id = 0
        self.work_pool_size = 5

    @staticmethod
    def get_time():
        return datetime.utcnow().replace(tzinfo=utc)

    def handle(self, *args, **options):
        last_playtime = PlayTime.objects.order_by('pk').last()
        if last_playtime is None:
            self.next_playtime_id = 1
        else:
            self.next_playtime_id = last_playtime.id + 1
        try:
            with get_lock("/tmp/check_servers_lock"), \
                    open_queue() as self.work_queue, \
                    open_queue() as self.less_important_work_queue, \
                    open_queue() as self.time_delay_queue, \
                    open_queue() as self.save_queue, \
                    open_queue() as self.deep_query_output, \
                    open_queue() as self.player_request_queue, \
                    open_queue() as self.player_response_queue, \
                    async_query.AsyncQuery(self.deep_query_output) \
                    as self.deep_query_handler, \
                    open_pool(self.work_pool_size, Command.do_work, (self,)) \
                    as pool, \
                    open_pool(1, Command.handle_time_delay_queue, (self,)), \
                    open_pool(1, Command.handle_deep_query_queue, (self,)):
                # We now have a lock guaranteeing (ish) some form of program
                # singularity.

                # Now fall into out main execution loop:
                old_work_size = 100
                while True:
                    # Fetch any servers that are not in the list.
                    self.append_new_servers()
                    # Check status of all of the processing threads
                    self.save_items()
                    work_size = self.work_queue.qsize()
                    # print("Loop", self.work_queue.qsize(),
                    # self.less_important_work_queue.qsize())
                    if work_size > 50 and work_size > old_work_size:
                        self.work_pool_size += 1
                        resize_pool(pool, self.work_pool_size)
                        print("Pool resized to " + str(self.work_pool_size))
                    revive_pool(pool)
                    old_work_size = work_size
                    self.fetch_players()
        except socket.error as error:
            if error.errno != errno.EADDRINUSE:
                raise

    def append_new_servers(self):
        for server in Server.objects.filter(pk__gt=self.max_server_id)[:100]:
            self.max_server_id = max(self.max_server_id, server.id)
            server.last_up_time = UpTime.objects.filter(
                server=server
            ).order_by('-checkTime').first()
            self.work_queue.put((WORK.BASIC_QUERY, server))

    def save_items(self):
        items = []
        try:
            while len(items) < 1000:
                items.append(self.save_queue.get(timeout=0.1))
        except NormalQueue.Empty:
            pass
        for i in xrange(10):
            try:
                self._save_items(items)
            except OperationalError:
                if i == 9:
                    raise
            else:
                break
        if self.save_queue.qsize() > 100:
            print("Saved " + str(len(items)) + " items. About " +
                  str(self.save_queue.qsize()) + " left in queue.")

    @staticmethod
    @atomic
    def _save_items(items):
        for item in items:
            item.save()
    # TIME DELAY QUEUE CODE

    def queue_later(self, queue_time, queue, item):
        self.time_delay_queue.put((queue_time, queue, item))

    def handle_time_delay_queue(self):
        list_of_queued_items = []
        while True:
            to_remove = []
            for rejoin_time, queue, values in list_of_queued_items:
                if rejoin_time < self.get_time():
                    if queue == QUEUES.WORK:
                        self.work_queue.put(values)
                    elif queue == QUEUES.LESS_IMPORTANT_WORK:
                        self.less_important_work_queue.put(values)
                    to_remove.append((rejoin_time, queue, values))
            for remove in to_remove:
                list_of_queued_items.remove(remove)
            try:
                while True:
                    data = self.time_delay_queue.get_nowait()
                    list_of_queued_items.append(data)
            except NormalQueue.Empty:
                # print(str(len(list_of_queued_items)) +
                #       " items waiting for queueing.")
                time.sleep(1)

    def do_work(self):
        while True:
            result = None
            try:
                result = self.work_queue.get_nowait()
            except NormalQueue.Empty:
                try:
                    result = self.less_important_work_queue.get_nowait()
                except NormalQueue.Empty:
                    time.sleep(0.02)
                    continue
            work_type, arguments = result
            if work_type == WORK.BASIC_QUERY:
                self.do_basic_query(arguments)

    def do_basic_query(self, server):
        up_time = UpTime(
            server=server,
            status=False,
            checkTime=self.get_time(),
            delta=600,
            playerCount=-1
        )
        try:
            delta = total_seconds(
                up_time.checkTime - server.last_up_time.checkTime
            )
            up_time.delta = min(delta, 600)
        except AttributeError:
            pass
        protocol_to_use = 0
        try:
            # Alternate if the query fails
            protocol_to_use = 1 - server.last_protocol
        except AttributeError:
            if server.protocol is not None and server.protocol < 0:
                protocol_to_use = 1
        server.last_protocol = protocol_to_use
        try:
            query = fake_client.query(
                (server.address, int(server.port)),
                protocol_number=protocol_to_use,
                timeout=3,
                cascade=False
            )
            del server.last_protocol
            up_time.status = True
            try:
                up_time.playerCount = int(query['players']['online'])
            except (KeyError, TypeError):
                pass
            try:
                query_protocol = query['version']['protocol']
                try:
                    protocol = int(query_protocol)
                    if protocol != server.protocol:
                        server.protocol = protocol
                        self.save_queue.put_nowait(server)
                except ValueError:
                    pass
            except (KeyError, TypeError):
                pass
        except IncorrectProtocolException:
            pass
        except KeyboardInterrupt:
            raise
        except Exception:
            pass
        server.last_up_time = up_time
        if up_time.status:
            if up_time.playerCount > 0 and self.is_online_mode(server):
                # We have players and are online
                self.deep_query_handler.query(
                    (server.address, server.port),
                    (server, )
                )
            self.queue_later(
                up_time.checkTime + SERVER_ONLINE_RESCAN_TIME,
                QUEUES.WORK,
                (WORK.BASIC_QUERY, server)
            )
        else:
            fails = 0
            try:
                fails = server.fail_count + 1
            except AttributeError:
                pass
            server.fail_count = fails
            self.queue_later(
                up_time.checkTime + SERVER_OFFLINE_RESCAN_TIME[
                    min(fails, len(SERVER_OFFLINE_RESCAN_TIME) - 1)
                ],
                QUEUES.WORK,
                (WORK.BASIC_QUERY, server)
            )
        self.save_queue.put_nowait(up_time)

    def handle_deep_query_queue(self):
        # Player name -> Server -> playtime
        player_server_playtimes = {}
        known_players = {}
        while True:
            while True:
                try:
                    server_id, players = self.deep_query_output.get_nowait()
                except NormalQueue.Empty:
                    break
                current_time = self.get_time()
                for player in [x.lower() for x in players]:
                    if player not in player_server_playtimes:
                        player_server_playtimes[player] = {}
                    if server_id in player_server_playtimes[player]:
                        playtime = player_server_playtimes[player][server_id]
                        if playtime.end_time < current_time - PLAYTIME_EXPIRY:
                            if hasattr(playtime, 'minecraft_account'):
                                self.save_queue.put_nowait(playtime)
                            del player_server_playtimes[player][server_id]
                    if server_id in player_server_playtimes[player]:
                        # Playtime is still valid
                        new_end_time = max(playtime.end_time, current_time)
                        if new_end_time > playtime.end_time:
                            playtime.duration += total_seconds(
                                new_end_time - playtime.end_time
                            )
                            playtime.end_time = new_end_time
                        if hasattr(playtime, 'minecraft_account'):
                            self.save_queue.put_nowait(playtime)
                    else:
                        playtime = PlayTime(
                            server=server_id,
                            duration=0,
                            end_time=current_time,
                            id=self.next_playtime_id
                        )
                        self.next_playtime_id += 1
                        player_data = known_players.get(player, None)
                        if player_data is not None and \
                                player_data['invalid'] < current_time:
                            playtime.minecraft_account = \
                                player_data['minecraft_account']
                        else:
                            self.player_request_queue.put_nowait(player)
                        player_server_playtimes[player][server_id] = playtime
            while True:
                try:
                    minecraft_accounts = self.player_response_queue.\
                        get_nowait()
                except NormalQueue.Empty:
                    pass
                for minecraft_account in minecraft_accounts:
                    name = minecraft_account.name.lower()
                    known_players[name] = {
                        'minecraft_account': minecraft_account,
                        'invalid': self.get_time() + PLAYER_EXPIRY,
                    }
                    if name in player_server_playtimes:
                        for playtime in player_server_playtimes[name].values():
                            playtime.minecraft_account = minecraft_account
                            self.save_queue.put_nowait(playtime)
            # print(player_server_playtimes.keys())
            if self.deep_query_output.qsize() > 10:
                print("Deep query queue length: " +
                      str(self.deep_query_output.qsize()))
            else:
                time.sleep(1)

    def fetch_players(self):
        players = []
        while len(players) < 100:
            try:
                players.append(self.player_request_queue.get_nowait())
            except NormalQueue.Empty:
                break
        if players:
            try:
                self.player_response_queue.put(
                    user_requester.request(players, 10).values()
                )
            except (socket.timeout, socket.error, socket.gaierror):
                pass

    def is_online_mode(self, server):
        try:
            if server.online_mode_time > self.get_time() - ONLINE_MODE_EXPIRY:
                if server.online_mode is None:
                    return False
                return server.online_mode
        except AttributeError:
            pass
        server.online_mode_time = self.get_time()
        try:
            online_mode = fake_client.check_online_mode(
                (server.address, int(server.port)),
                protocol_number=server.protocol,
                timeout=3,
                username="FindAServer"
            )
        except (DisconnectException,
                IncorrectProtocolException,
                socket.error,
                socket.timeout):
            # TODO: Report error
            online_mode = False
        if online_mode != server.online_mode:
            server.online_mode = online_mode
            self.save_queue.put_nowait(server)
        return online_mode
