import socket

from Crypto import Random
from Crypto.PublicKey import RSA


def vote(addr, pub_key, service_name, username, ip, timestamp, timeout=10):
    data = "\n".join([
        "VOTE",
        str(service_name),
        str(username),
        str(ip),
        str(timestamp),
        ""
    ])
    if len(data) > 256:
        raise Exception("Data string was too long %i > %i", len(data), 256)
    pad_len = 256 - 3 - len(data)
    r = Random.new()
    random = []
    while len(random) < pad_len:
        random += [x for x in r.read(pad_len-len(random)) if 0 < ord(x) < 255]
    data = "\x00\x02" + "".join(random) + "\x00" + data
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect(addr)
    status = s.recv(4096)
    if status[:8] != "VOTIFIER":
        raise Exception("Did not receive votifier version header.")
    enc = RSA.importKey(str(pub_key)).encrypt(data, 0)[0]
    send_message(s, enc)


def send_message(conn, message):
    start = size = len(message)
    while size:
        size -= conn.send(message[start-size:])
