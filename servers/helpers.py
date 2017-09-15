from datetime import timedelta, datetime
import math

from django.db.models import Sum, Max, Count

from servers.models import MinecraftAccount, Server


def total_seconds(delta_time):
    if hasattr(delta_time, "total_seconds"):
        return delta_time.total_seconds()
    seconds = (delta_time.seconds + delta_time.days * 24 * 3600)
    microseconds = seconds * 10 ** 6 + delta_time.microseconds
    return microseconds / 10 ** 6


def top_players_by_time(server_id=None, date_min=None):
    query = MinecraftAccount.objects
    if server_id is not None:
        if date_min is None:
            query = query.filter(playtime__server=server_id)
        else:
            query = query.filter(
                playtime__server=server_id,
                playtime__end_time__gte=date_min
            )
    elif date_min is not None:
        query = query.filter(playtime__end_time__gte=date_min)
    return query.annotate(
        time=Sum('playtime__duration'),
        last_on=Max('playtime__end_time')
    ).order_by('-time')


def top_players_by_votes(server_id=None, date_min=None):
    query = MinecraftAccount.objects
    if server_id is not None:
        if date_min is None:
            query = query.filter(vote__server=server_id)
        else:
            query = query.filter(
                vote__server=server_id,
                vote__time__gte=date_min
            )
    elif date_min is not None:
        query = query.filter(vote__time__gte=date_min)
    return query.annotate(votes=Count('vote')).order_by('-votes')


def top_servers_by_time(player_id=None):
    query = Server.objects
    if player_id is not None:
        query = query.filter(playtime__minecraft_account=player_id)
    return query.annotate(
        time=Sum('playtime__duration'),
        last_on=Max('playtime__end_time')
    ).order_by('-time')


def player_count_history(start, end, period, data):
    period_sec = total_seconds(period)
    length = total_seconds(end - start) / period_sec
    history = [0] * int(math.ceil(length))
    for uptime in data:
        offset = int(total_seconds(uptime['checkTime'] - start) / period_sec)
        history[offset] = uptime['playerCount']
    res = []
    cur = start
    for val in history:
        res.append(('new Date(%s000)' % cur.strftime("%s"), val))
        cur += timedelta(seconds=period_sec)
    return res


def player_count_history_old(start, end, period, data):
    period_sec = total_seconds(period)
    length = total_seconds(end - start) / period_sec
    history = [{} for _ in xrange(int(math.ceil(length)))]
    for uptime in data:
        offset_start = int(total_seconds(
            (uptime['checkTime'] - timedelta(seconds=uptime['delta'])) - start
        ) / period_sec)
        offset_end = int(math.ceil(total_seconds(
            uptime['checkTime'] - start
        ) / period_sec) + 1)
        for time in history[offset_start:offset_end]:
            time[uptime['server_id']] = max(
                time.pop(uptime['server_id'], 0),
                uptime['playerCount']
            )
    res = []
    cur = start
    for val in history:
        res.append(
            ('new Date(%s000)' % cur.strftime("%s"), sum(val.itervalues()))
        )
        cur += timedelta(seconds=period_sec)
    return res


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        client_ip = x_forwarded_for.split(',')[0]
    else:
        client_ip = request.META.get('REMOTE_ADDR')
    return client_ip


def has_ads(request, context=None):
    if context is not None:
        context['has_ads'] = has_ads(request)
        context['check_ads'] = True
    return 'has_ads' in request.session and request.session['has_ads'] > int(
        (datetime.utcnow() - timedelta(minutes=30)).strftime("%s"))


def get_allowed_votes(request):
    allowed = 1
    if request.user.is_authenticated():
        allowed += 1
    if has_ads(request):
        allowed += 1
    return allowed
