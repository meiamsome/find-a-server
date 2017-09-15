import httplib
import json
from datetime import datetime

from django.utils.timezone import utc

from servers.models import MinecraftAccount, Names


def request(player_list, timeout=None):
    if len(player_list) > 100:
        res = {}
        for i in xrange(len(player_list) / 100 + 1):
            res += request([100 * i, 100 * (i + 1)])
        return res
    conn = httplib.HTTPSConnection("api.mojang.com", timeout=timeout)
    req = '["' + '", "'.join(player_list) + '"]'
    conn.request("POST", "/profiles/minecraft", req)
    resp = conn.getresponse()
    if resp.status != 200:
        raise Exception(
            "Could not request user: Status Code " + str(resp.status) +
            ", " + str(req) + ": " + str(conn)
        )

    accounts = json.loads(resp.read())
    now = datetime.utcnow().replace(tzinfo=utc)
    keyed_by_username = dict()
    for user in accounts:
        user['UUID'] = int(user['id'], 16)
        keyed_by_username[user['name'].lower()] = user

    result = dict()

    # Get as many as we can in one go.
    all_players = MinecraftAccount.objects.filter(
        name__in=keyed_by_username.keys()
    )
    for user in all_players:
        try:
            keyed_by_username[user.name.lower()]
        except KeyError:  # Occurs if the user has changed case of their name.
            continue
        if user.UUID != keyed_by_username[user.name.lower()]['UUID']:
            user.name = None
            user.save()
            Names.objects.filter(minecraft_account=user, end=None).update(
                end=now
            )
            continue
        if user.name != keyed_by_username[user.name.lower()]['name']:
            user.name = keyed_by_username[user.name.lower()]['name']
            user.save()
            Names.objects.filter(minecraft_account=user, end=None).update(
                end=now
            )
            Names.objects.create(
                minecraft_account=user,
                name=user.name,
                end=None,
                start=now
            )
        result[user.name] = user
        keyed_by_username.pop(user.name.lower(), None)

    # Everyone else
    for _, user in keyed_by_username.iteritems():
        user['UUID'] = int(user['id'], 16)
        obj = None
        try:
            obj = MinecraftAccount.objects.get(UUID=user['UUID'])
            if obj is not None and (
                    obj.name is None or obj.name != user['name']):
                if obj.name is not None:
                    Names.objects.filter(
                        minecraft_account=obj,
                        end=None
                    ).update(end=now)
                obj.name = user['name']
                obj.save()
        except MinecraftAccount.DoesNotExist:
            pass
        if obj is None:
            obj = MinecraftAccount.objects.create(
                name=user['name'],
                UUID=user['UUID']
            )
        Names.objects.create(
            minecraft_account=obj,
            name=user['name'],
            end=None,
            start=now
        )
        result[obj.name] = obj
    return result
