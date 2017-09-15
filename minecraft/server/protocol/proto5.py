import httplib
import json
import random

from Crypto.Cipher import AES
from Crypto.Hash import SHA

from minecraft.types import short, varint, string
from minecraft.types.exceptions import ProtocolException


def handle(server, conn, addr, handshake, data_buffer):
    if handshake[3] == 1:
        handle_query(server, conn, addr, handshake, data_buffer)
    elif handshake[3] == 2:
        handle_login(server, conn, addr, handshake, data_buffer)
    else:
        conn.close()
        raise RuntimeError("Unknown mode " + str(handshake[3]))


def handle_query(server, conn, addr, handshake, data_buffer):
    while True:
        pack = get_packet(conn, data_buffer)
        if pack is None:
            # print("Disconnect.")
            return
        pid, start = varint.from_stream(pack)
        if pid == 0:
            # print("Received Query, sending data.")
            message = """
            {
                "version": {
                    "name": "Not a Sever",
                    "protocol": %i
                },
                "players": {
                    "max": 0,
                    "online": 0,
                    "sample":[]
                },
                "description": {
                    "text":"Find A Server Verification Service\nPlease log in to get your code.",
                    "color":"white"
                }
            }""" % handshake[0]
            message = "\x00" + string.to_stream(message.replace(' ', ' '))
            send_message(conn, string.to_stream(message))
        elif pid == 1:
            # print("Ping")
            send_message(conn, string.to_stream("".join(pack)))
        else:
            print("Client misbehaving (id: " + str(pid) + ")")
            conn.close()
            return


def handle_login(server, conn, addr, handshake, data_buffer):
    verify_token = ""
    username = ""
    while True:
        pack = get_packet(conn, data_buffer)
        if pack is None:
            # print("Disconnect.")
            return
        pid, start = varint.from_stream(pack)
        print(pid)
        if pid == 0:
            # Login start
            username, start = string.from_stream(pack[start:])
            username = "".join(username)
            # print("User " + username + " starting login.")
            pkeystr = server['key'].publickey().exportKey('DER')
            verify_size = 4
            while verify_size:
                verify_token += chr(random.randrange(255))
                verify_size -= 1
            message = "\x01" + string.to_stream("")
            message += short.to_stream(len(pkeystr)) + pkeystr
            message += short.to_stream(len(verify_token)) + verify_token
            send_message(conn, string.to_stream(message))
        elif pid == 1:
            sec_len, startinc = short.from_stream(pack[start:])
            start += startinc
            secret = pack[start:start+sec_len]
            start += sec_len
            tok_len, startinc = short.from_stream(pack[start:])
            start += startinc
            token = "".join(pack[start:start+tok_len])
            tok = server['key'].decrypt(token)[-len(verify_token):]
            if tok != verify_token:
                # print("Client did not encrypt token correctly (%s != %s)"
                #       % (tok, verify_token))
                send_message(conn, string.to_stream(
                    "\x00"+string.to_stream(
                        "{'text':'Failed to validate token.'}"
                    )
                ))
                conn.close()
                return
            shared_secret = server['key'].decrypt("".join(secret))[-16:]
            cipher = AES.new(shared_secret, AES.MODE_CFB, shared_secret,
                             segment_size=8)
            user = None
            try:
                shahash = SHA.new("")
                shahash.update(shared_secret)
                shahash.update(server['key'].publickey().exportKey('DER'))
                result = int(shahash.hexdigest(), 16)
                if result > 1 << 159:
                    result ^= (1 << 160) - 1
                    result = "-%x" % (result + 1)
                else:
                    result = "%x" % result
                headers = {
                    "Content-type": "application/json",
                }
                mcrequest = httplib.HTTPSConnection("sessionserver.mojang.com")
                mcrequest.request(
                    "GET",
                    "/session/minecraft/hasJoined?username="
                    "%s&serverId=%s" % (username, result),
                    None,
                    headers
                )
                resp = mcrequest.getresponse()
                if resp.status == 200:
                    user = json.loads(resp.read())
                    user['username'] = username
                else:
                    print("Status for request: %i %s" % (
                        resp.status, resp.reason))
            except Exception, e:
                print("Exception.", e)
            if user is None:
                print("Could not verify account with Mojang")
                send_message(
                    conn,
                    string.to_stream("\x00" + string.to_stream(
                        "{'text':\"Failed to query Minecraft's "
                        "Authentication Server.\"}"
                    )),
                    cipher
                )
                conn.close()
                return
            uuid = user['id']
            uuid = uuid = uuid[:8] + "-" + uuid[8:12] + "-" + uuid[12:16]
            uuid += "-" + uuid[16:20] + "-" + uuid[20:]
            user['formatted_id'] = uuid
            # print("Successful login. User %s authenticated." % user['username'])
            # Find A Server Modification
            # TODO
            code = None
            try:
                # TODO: Move shared secret to a settings file.
                shahash = SHA.new(
                    user['formatted_id'].upper() + "SHAREDSECRET"
                )
                # TODO: Move domain to a settings file.
                codecon = httplib.HTTPSConnection("find-a-server.com")
                codecon.request(
                    "GET",
                    "/players/%s/verify_token/?hash=%s" % (
                        user['formatted_id'].upper(),
                        shahash.hexdigest()
                    )
                )
                resp = codecon.getresponse()
                if resp.status == 200:
                    code = resp.read()
                else:
                    print("Received HTTP %s %s from find-a-server.com" % (
                        resp.status,
                        resp.reason
                    ))
            except Exception, e:
                print("Exception", e)
            if code is None:
                print("Could not fetch key.")
                send_message(conn, string.to_stream("\x00"+string.to_stream(
                    "{'text':\"Failed to get a key for your account.\"}"
                )), cipher)
                conn.close()
                return
            send_message(conn, string.to_stream("\x00"+string.to_stream("""
            {
                'text': "Your unique activation code is:\\n\\n",
                'extra': [
                    {
                        'text': '%s\\n\\n\\n\\n\\n',
                        'color': 'gold'
                    },
                    "Thank you for using Find A Sever."
                ]
            }""" % code)), cipher)
            conn.close()
            return
            # End Find A Server Modification
            # send_message(conn, string.to_stream("\x02" + string.to_stream(
            #     user['formatted_id']
            # ) + string.to_stream(user['username'])), cipher)
            # return handle_play(server, conn, addr, handshake, data_buffer,
            #                    cipher)
        else:
            print("Client sent unknown packet " + str(pid) + ". "
                  "Packet discarded.", pack)


def handle_play(server, conn, addr, handshake, data_buffer, cipher):
    while True:
        pack = get_packet(conn, data_buffer, cipher)
        if pack is None:
            print("Disconnect.")
            return
        pid, start = varint.from_stream(pack)
        print("Packet %s " % pid)


def disconnect_client(conn, reason="Generic Disconnect.", cipher=None):
    send_message(conn, string.to_stream('\x40' + string.to_stream(
        "{'text':\"%s\"}" % reason)
    ), cipher)
    conn.close()


def send_message(conn, message, cipher=None):
    if cipher is not None:
        message = cipher.encrypt("".join(message))
    start = size = len(message)
    while size:
        size -= conn.send(message[start-size:])


def get_packet(conn, data_buffer, cipher=None):
    while True:
        try:
            length, stop = varint.from_stream(data_buffer)
        except ProtocolException:
            data = conn.recv(4096)
            if not data:
                conn.close()
                return None
            if cipher is not None:
                data = cipher.decrypt("".join(data))
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
