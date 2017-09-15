import base64
from collections import OrderedDict
from datetime import datetime, timedelta

from Crypto import Random
from Crypto.Hash import SHA

from django.core.cache import cache
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.urlresolvers import reverse
from django.db import connection
from django.db.models import Q, Sum, Max, Count
from django.http import Http404, HttpResponsePermanentRedirect, HttpResponse, \
    HttpResponseRedirect
from django.shortcuts import render, get_object_or_404
from django.utils.timezone import utc

from servers.models import Server, MinecraftAccount, UpTime, PlayTime, \
    UpTimeAggregate, Names
from servers import forms
from servers.templatetags import myfilters
from servers.helpers import player_count_history, top_servers_by_time, \
    top_players_by_time


_DEFAULT_PER_PAGE = 10

_SERVERS_PER_PAGE = _DEFAULT_PER_PAGE
_PLAYERS_PER_PAGE = _DEFAULT_PER_PAGE
_PLAYER_DETAILS_PER_PAGE = _DEFAULT_PER_PAGE


# Create your views here.
def index(request):
    page_num = request.GET.get('page')
    if page_num is None:
        page_num = 1
    else:
        try:
            page_num = int(page_num)
        except ValueError:
            raise Http404
        if str(page_num) != request.GET.get('page'):
            raise Http404
        if page_num == 1:
            return HttpResponsePermanentRedirect(reverse('servers:index'))
    pages = Paginator(
        Server.objects.filter(rank__isnull=False).order_by("rank"),
        _SERVERS_PER_PAGE
    )
    try:
        page = pages.page(page_num)
    except (EmptyPage, PageNotAnInteger):
        raise Http404
    cann = reverse('servers:index')
    if page.number != 1:
        cann += "?page=" + str(page.number)
    now = datetime.utcnow().replace(tzinfo=utc)
    for server in page:
        server.online_players = MinecraftAccount.objects.filter(
            playtime__server=server.id,
            playtime__end_time__gte=now - timedelta(minutes=5)
        ).annotate(
            duration=Sum("playtime__duration")
        ).order_by('-duration')
        server.online_player_count = len(server.online_players)
        server.online_players = server.online_players[:10]
    return render(request, 'servers/index.html', {
        'page': page,
        'canonical': cann,
    })


def submit_server(request):
    servers = []
    if request.method == 'POST':
        form = forms.SubmitServerForm(request.POST)
        if form.is_valid():
            return HttpResponseRedirect(
                Server.objects.create(
                    name=form.cleaned_data['server_name'],
                    address=form.cleaned_data['address'][0],
                    port=form.cleaned_data['address'][1]
                ).get_absolute_url()
            )
    else:
        form = forms.SubmitServerForm()
    return render(request, 'servers/submit.html', {
        'form': form,
        'servers': servers,
    })


def player_list(request):
    value = cache.get("player_list")
    if value:
        context = dict(value[1])
        context['valid'] = True
        return render(request, value[0], context)
    context = {
        'valid': False,
        'find_player_form': forms.PlayerHistoryForm(),
    }
    return render(request, "players/index.html", context)


def player_list_with_server(request, server_id=None):
    return render(request, *player_list_no_cache(request, server_id))


def player_list_no_cache(request, server_id=None):
    # l = logging.getLogger('django.db.backends')
    # l.setLevel(logging.DEBUG)
    # l.addHandler(logging.StreamHandler())
    now = datetime.now() # utcnow().replace(tzinfo=utc)
    if server_id is None:
        context = {
            'top_players': list(
                top_players_by_time(date_min=now - timedelta(weeks=1))[:10]
            ),
            'online': list(
                MinecraftAccount.objects.filter(
                    playtime__end_time__gte=now - timedelta(minutes=5)
                ).annotate(
                    duration=Sum("playtime__duration")
                ).order_by('-duration')[:10]
            ),
        }
    else:
        context = {
            'top_players': MinecraftAccount.objects.filter(
                playson=1
            ).annotate(
                time=Sum('playtime__duration'),
                last_on=Max('playtime__end_time')
            ).order_by('-time')[:10],
        }
    graphs = [
        {
            'element': 'player-count-graph',
            'type': 'AreaChart',
            'package': 'corechart',
            'cols': [
                {
                    'id': 'Date',
                    'type': 'date',
                },
                {
                    'id': 'Players',
                    'type': 'number',
                },
            ],
        }
    ]

    if server_id is None:
        context['find_player_form'] = forms.PlayerHistoryForm()
        query = "SELECT `checkTime`, SUM(`playerCount`) as players FROM "\
                "`servers_uptimeaggregate` WHERE checkTime > UTC_TIMESTAMP() "\
                "- INTERVAL 1 WEEK GROUP BY `checkTime`"
        with connection.cursor() as cursor:
            cursor.execute(query)
            data = cursor.fetchall()
            if data:
                rounded_now = now.replace(
                    second=0,
                    microsecond=0,
                    minute=10*(now.minute/10)
                )
                graphs[0]['data'] = player_count_history(
                    rounded_now - timedelta(weeks=1),
                    rounded_now,
                    timedelta(minutes=30),
                    (
                        {
                            'checkTime': up[0],
                            'playerCount': up[1],
                        } for up in data
                    )
                )
    else:
        graphs[0]['data'] = player_count_history(
            datetime.utcnow().replace(tzinfo=utc) - timedelta(weeks=1),
            datetime.utcnow().replace(tzinfo=utc), timedelta(minutes=30),
            UpTime.objects.filter(
                server=server_id,
                checkTime__gte=(
                    datetime.utcnow().replace(tzinfo=utc) - timedelta(weeks=1)
                ),
                status=1
            ).values('checkTime', 'server_id', 'delta', 'playerCount')
        )
    context['graphs'] = graphs
    return 'players/index.html', context


def player_detail(request, player_uuid, server_id=None):
    # __iexact because django/mysql bug.
    player = get_object_or_404(
        MinecraftAccount,
        UUID__iexact=int("".join(player_uuid.split("-")), 16)
    )
    now = datetime.utcnow().replace(tzinfo=utc)
    context = {
        'player': player,
        'top_servers': top_servers_by_time(player.id)[:5],
        'recent_playtime': PlayTime.objects.filter(
            minecraft_account=player
        ).order_by('-end_time')[:10],
        'votes': Server.objects.filter(
            Q(vote__time__gte=now - timedelta(weeks=1)) & (
                Q(vote__minecraft_account=player) |
                Q(vote__minecraft_name=player.name)
            )
        ).annotate(count=Count('vote__time')),
    }
    data = PlayTime.objects.filter(
        minecraft_account=player,
        end_time__gte=now - timedelta(weeks=1)
    ).select_related('server')
    if data:
        context['graphs'] = [
            {
                'element': 'playtime-graph',
                'type': 'Timeline',
                'package': 'timeline',
                'cols': [
                    {
                        'id': 'Server',
                        'type': 'string',
                    },
                    {
                        'id': 'Start',
                        'type': 'date',
                    },
                    {
                        'id': 'End',
                        'type': 'date',
                    },
                ],
                'data': (
                    (
                        "'%s'" % s.server.name,
                        "new Date(%s)" % (
                            (s.end_time - timedelta(
                                seconds=s.duration + 1
                            )).strftime("%s") + "000"
                        ),
                        "new Date(%s)" % (
                            s.end_time.strftime("%s") + "000"
                        ),
                    ) for s in data
                ),
                'options': """{
                    hAxis: {
                        viewWindowMode:'explicit',
                        viewWindow: {
                            min: new Date(%s),
                            max: new Date(%s)
                        }
                    }
                }""" % (
                    (now - timedelta(weeks=4)).strftime("%s") + "000",
                    now.strftime("%s") + "000",
                ),
            },
        ]

    # pages = Paginator(Server.objects.all().order_by("-name"),
    #                   _SERVERS_PER_PAGE)
    # TODO
    return render(request, 'players/detail.html', context)


def player_verify(request, player_uuid):
    player = get_object_or_404(
        MinecraftAccount,
        UUID__iexact=int("".join(player_uuid.split("-")), 16)
    )
    if request.method == 'POST':
        form = forms.PlayerVerifyForm(request.POST)
        if form.is_valid() and request.user.is_authenticated():
            if form.cleaned_data['token'] == player.verification_code:
                # TODO: timestamp
                player.owner = request.user
                player.save()
    else:
        form = forms.PlayerVerifyForm()
    return render(request, 'players/verify.html', {
        'player': player,
        'form': form
    })


# Called by the minecraft server to fetch a token for a user.
def player_verify_token(request, player_uuid):
    if not request.GET.get('hash'):
        raise Http404
    # TODO: Move Shared secret to settings?
    shahash = SHA.new(player_uuid + "SHAREDSECRET").hexdigest()
    if shahash != request.GET.get('hash'):
        print(shahash, request.GET.get('hash'))
        raise Http404
    player = get_object_or_404(
        MinecraftAccount,
        UUID__iexact=int("".join(player_uuid.split("-")), 16)
    )
    player.verification_code = base64.b64encode(Random.new().read(6))
    player.save()
    # TODO add a timestamp
    return HttpResponse(player.verification_code)


def statistics(request):
    value = cache.get("statistics")
    if value:
        return render(request, *value)
    return render(request, *statistics_no_cache(request))


def statistics_no_cache(request):
    stats = OrderedDict()
    servers = Server.objects.count()
    hour_pings = UpTime.objects.filter(
        checkTime__gte=datetime.utcnow().replace(tzinfo=utc) -
        timedelta(hours=1)
    ).count()
    delta = "No pings in the last hour"
    if hour_pings:
        delta = myfilters.delta(3600 * servers // hour_pings)
    players = MinecraftAccount.objects.count()
    changes = Names.objects.count() - players
    uptime_data = UpTimeAggregate.objects.aggregate(time=Sum('up_time'), total=Sum('total_time'))
    stats['General'] = OrderedDict([
        ('Servers Tracked', ("%i servers" % servers,)),
        ('Players Tracked', ('%i players' % players,)),
        ('Players Tracked As Percentage', (
            "%.2f %%" % (players/float(25000000/100)),
        )),
        ('Name Changes Tracked', (
            '%i changes' % changes,
            '/players/name-changes/'
        )),
        ('Playtime Tracked', (
            "%i hours" % (
                PlayTime.objects.aggregate(time=Sum('duration'))['time'] / 3600.0
            ),
        )),
        ('Uptime Tracked', (
            '%i hours' % (uptime_data['time'] / 3600.0),
        )),
        ('Downtime Tracked', (
            '%i hours' % (
                (uptime_data['total'] - uptime_data['time']) / 3600.0
            ),
        )),
        # ('Server Pings', (
        #     '%i requests' % UpTime.objects.order_by('-id').first().id,
        # )),
        ('Server Pings in the Last Hour', ('%i requests' % hour_pings,)),
        ('Average Ping Delta', (delta,))
    ])

    stats['Servers'] = OrderedDict()
    server = top_servers_by_time().first()
    stats['Servers']['Most Playtime'] = (
        "%s (%i hours)" % (server.name, server.time / 3600),
        server.get_absolute_url(),
    )
    stats['Players'] = OrderedDict()
    player = top_players_by_time().first()
    stats['Players']['Most Playtime'] = (
        "%s (%i hours)" % (player.name, player.time / 3600),
        player.get_absolute_url(),
    )
    playtime = PlayTime.objects.order_by("-duration").first()
    stats['Players']['Longest Session'] = (
        "%s (%i hours)" % (
            playtime.minecraft_account.name,
            playtime.duration/3600,
        ),
        playtime.minecraft_account.get_absolute_url(),
    )
    # TODO: Work out how to do this one
    # stats['Players']['Most Servers Played On'] = (
    #     "%s (%i servers)" % (
    #         player.name,
    #         player.nservs
    #     ),
    #     player.get_absolute_url()
    # )
    # player = MinecraftAccount.objects.annotate(
    #     sessions=Count('playson')
    # ).order_by('-sessions').first()
    # result = PlayTime.objects.annotate(
    #     sessions=Count('minecraft_account')
    # ).order_by('-sessions').first()
    # player = result.minecraft_account
    # stats['Players']['Most Play Sessions'] = (
    #     "%s (%i sessions)" % (player.name, result.sessions),
    #     player.get_absolute_url()
    # )
    stats['Players']['Online in the Last Hour'] = (
        "%i players" % MinecraftAccount.objects.annotate(
            last_on=Max('playtime__end_time')
        ).filter(
            last_on__gte=datetime.utcnow().replace(tzinfo=utc) -
            timedelta(hours=1)
        ).count(),
    )

    return 'servers/stats.html', {'stats': stats}


def ad(request):
    if hasattr(request, 'session') and request.session.session_key:
        request.session['has_ads'] = int(datetime.utcnow().strftime("%s"))
    return render(request, 'servers/ads.js')
