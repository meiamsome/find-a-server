from datetime import datetime, timedelta
import base64

from Crypto import Random
from dns import resolver

from django.db import connection, IntegrityError
from django.db.models import Sum
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.shortcuts import render, get_object_or_404
from django.utils.timezone import utc

from servers.models import Server, MinecraftAccount, UpTimeAggregate, Vote, \
    ServerVerificationKey as SVK, PlayTime, ExtraServerData
from servers.helpers import top_players_by_time, player_count_history, \
    top_players_by_votes, get_client_ip, get_allowed_votes, \
    total_seconds, has_ads
from servers import forms
from servers import server_ownership_checker


def server_detail(request, server_id):
    server = get_object_or_404(Server, pk=server_id)
    now = datetime.utcnow().replace(tzinfo=utc)
    players_by_time = top_players_by_time(
        server_id,
        date_min=now - timedelta(weeks=1)
    )
    context = {
        'server': server,
        'top_players': players_by_time[:10],
        'top_voters': top_players_by_votes(
            server_id,
            date_min=now - timedelta(weeks=1)
        )[:10],
        'online': MinecraftAccount.objects.filter(
            playtime__server=server_id,
            playtime__end_time__gte=now - timedelta(minutes=5)
        ).annotate(
            duration=Sum("playtime__duration")
        ).order_by('-duration')[:10],
    }

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT SUM(`up_time`) as up, SUM(`total_time`) as total FROM "
            "`servers_uptimeaggregate` WHERE checkTime > NOW() - INTERVAL "
            "1 WEEK AND server_id = %s ",
            [server_id]
        )
        row = cursor.fetchone()
        if row and row[1] and int(row[1]) != 0:
            uptime = (100 * float(row[0]) / float(row[1]))
            context['uptime'] = "%.2f%%" % uptime
        else:
            uptime = 0
            context['uptime'] = "Awaiting data"
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
            'data': player_count_history(
                now - timedelta(weeks=1),
                now,
                timedelta(minutes=60),
                UpTimeAggregate.objects.filter(
                    server=context['server'],
                    checkTime__gte=now - timedelta(weeks=1)
                ).values('checkTime', 'playerCount')
            ),
        },
    ]

    last501 = list(PlayTime.objects.filter(
        server=server,
        end_time__gte=now - timedelta(weeks=1)
    ).order_by('-end_time')[0:51])
    if len(last501) > 5:
        if len(last501) != 51:
            last500 = last501
            last_end_time = None
        else:
            last500 = last501[:-1]
            last_end_time = last501[-1].end_time
        if last_end_time is None or (now - last_end_time > timedelta(hours=3)):
            # playtime_by_players = {}
            # sum_by_player = {}
            # for x in last500:
            #     if last_end_time is not None and last_end_time > x.end_time \
            #           - timedelta(seconds=x.duration):
            #         x.duration = total_seconds(x.end_time - last_end_time)
            #     try:
            #         playtime_by_players[x.minecraft_account_id].append(x)
            #         sum_by_player[x.minecraft_account_id] += x.duration
            #     except:
            #         playtime_by_players[x.minecraft_account_id] = [x]
            #         sum_by_player[x.minecraft_account_id] = x.duration
            # last500 = []
            # for key in sorted(sum_by_player, key=sum_by_player.get,
            #                   reverse=True):
                # last500 += playtime_by_players[key]
            graphs.append({
                'element': 'playtime-graph',
                'type': 'Timeline',
                'package': 'timeline',
                'cols': [
                    {
                        'id': 'Username',
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
                        (
                            "'%s'" % s.minecraft_account.name,
                            "new Date(%s)" % (
                                (s.end_time - timedelta(
                                    seconds=s.duration + 1
                                )).strftime("%s") + "000"
                            ),
                            "new Date(%s)" % (
                                s.end_time.strftime("%s") + "000")
                            ),
                        ) for s in last500
                    ),
            })
            context['show_last_playtimes'] = True
    context['graphs'] = graphs
    allowed = get_allowed_votes(request)
    context['allowed_votes'] = allowed
    votes = Vote.objects.filter(
        server=server,
        ip=get_client_ip(request),
        time__gt=now - timedelta(hours=24)
    ).order_by('time')
    count = len(votes)
    context['vote_count'] = count
    context['votes_left'] = allowed - count
    if count >= allowed:
        has_ads(request, context)
        context['next_expire'] = total_seconds(
            (votes[count - allowed].time + timedelta(hours=24)) - now
        )
    context['has_votifier'] = ExtraServerData.objects.filter(
        server=server,
        type=ExtraServerData.VOTIFIER
    ).exists()
    form = forms.VoteForm(request)
    if request.method == 'POST':
        if form.is_valid() and count < allowed:
            vote = Vote(server=server, ip=get_client_ip(request), time=now,
                        submitted=False if context['has_votifier'] else None)
            try:
                vote.minecraft_account = MinecraftAccount.objects.get(
                    pk=form.cleaned_data['account']
                )
                vote.minecraft_name = vote.minecraft_account.name
            except KeyError:
                vote.minecraft_name = form.cleaned_data['account_name']
                try:
                    vote.minecraft_account = MinecraftAccount.objects.get(
                        name=vote.minecraft_name
                    )
                except MinecraftAccount.DoesNotExist:
                    pass
            vote.save()
            messages.add_message(
                request,
                messages.SUCCESS,
                "Your vote has been submitted. Thank you!"
            )
            return HttpResponseRedirect(server.get_absolute_url())
    context['vote_form'] = form
    context['total_playtime'] = PlayTime.objects.filter(
        end_time__gt=now - timedelta(weeks=1),
        server=server
    ).aggregate(Sum('duration'))['duration__sum']
    if context['total_playtime'] is None:
        context['total_playtime'] = 0
    context['total_votes'] = Vote.objects.filter(
        time__gt=now - timedelta(weeks=1),
        server=server
    ).count()
    context['total_players'] = players_by_time.count()
    if context['has_votifier']:
        context['votifier_outstanding'] = Vote.objects.filter(
            server=server,
            submitted=False
        ).count()
    # Score the server.
    score = context['total_votes'] * 1000
    score += context['total_playtime']/60
    score += context['total_players'] * 10
    if context['has_votifier']:
        vot_multi = 1.5
        if context['votifier_outstanding'] > 2:
            vot_multi -= (context['votifier_outstanding'] - 2)/20
        score *= min(1, vot_multi)
    score = int(score * (100 + uptime)/float(100))
    if server.score != score:
        server.score = score
        # Don't do this, causes too many errors :(
        # server.save(update_fields=['score'])

    # Handle the top image TODO: Make this user settable
    images = (
        (
            '/static/stock_images/minecraft-354458_1280.png',
            'right -233px',
            True
        ),
        (
            '/static/stock_images/minecraft-655158_1280.jpg',
            'right -137px',
            True
        ),
        (
            '/static/stock_images/minecraft-655956_1280.jpg',
            'right -130px',
            True
        ),
        (
            '/static/stock_images/minecraft-354463_1280.png',
            'center -207px',
            True
        ),
        (
            '/static/stock_images/minecraft-529463_1280.jpg',
            'center -238px',
            True
        ),
        (
            '/static/stock_images/minecraft-655908_1280.png',
            'center -225px',
            True
        ),
    )
    context['cover_image'] = images[server.id % len(images)]
    return render(request, 'servers/detail.html', context)


def server_verify(request, server_id):
    server = get_object_or_404(Server, pk=server_id)
    context = {'server': server, 'allow_dns': True, }
    if request.user.is_authenticated():
        try:
            resolver.query(server.address, 'A')
        except resolver.NXDOMAIN:
            context['allow_dns'] = False
        except:
            pass
        codes = SVK.objects.filter(
            server=server,
            user=request.user
        )
        code_types = set([
            SVK.MOTD_METHOD,
            SVK.DNS_METHOD
        ])
        verification = {}
        for code in codes:
            code_types.remove(code.verification_mode)
            verification[code.verification_mode] = code
        if code_types:
            rand = Random.new()
            for code_type in code_types:
                tries = 0
                while tries < 5:
                    tries += 1
                    try:
                        code = SVK(
                            server=server,
                            user=request.user,
                            verification_mode=code_type,
                            verification_code=base64.b64encode(rand.read(18))
                        )
                        code.save()
                        verification[type] = code
                    except IntegrityError:
                        continue
                    break
                else:
                    messages.add_message(
                        request,
                        messages.ERROR,
                        "Failed to generate a key. If you need the key, "
                        "you can refresh the page to try again."
                    )
        if SVK.DNS_METHOD in verification:
            context['verification1'] = verification[SVK.DNS_METHOD]
        if SVK.MOTD_METHOD in verification:
            context['verification2'] = verification[SVK.MOTD_METHOD]
    return render(request, 'servers/verify.html', context)


def server_verify_check(request, server_id, verify_type):
    server = get_object_or_404(Server, pk=server_id)
    if request.user.is_authenticated():
        try:
            code = SVK.objects.get(
                server=server,
                user=request.user,
                verification_mode=int(verify_type) - 1
            )
        except SVK.DoesNotExist:
            pass
        else:
            (
                old_valid,
                new_valid,
                dns_records,
                motd,
            ) = server_ownership_checker.challenge_ownership(server, code)
            if old_valid is not True and new_valid is True:
                server.owner = request.user
                server.verification = code
                server.save()
                messages.add_message(
                    request,
                    messages.SUCCESS,
                    "You are now the owner of this server."
                )
            elif new_valid is not True:
                mess = "Your verification check failed. "
                if code.verification_mode == SVK.DNS_METHOD and dns_records:
                    mess += "Your DNS server reported the following results:\n"
                    mess += "\n".join(dns_records)
                elif code.verification_mode == SVK.MOTD_METHOD:
                    if motd:
                        mess += "Your server's MOTD currently reads: " + motd
                    else:
                        mess += "We failed to check your server's MOTD. " \
                                "Please try again"
                messages.add_message(request, messages.ERROR, mess)
            else:
                # new_valid is True
                # old_valid is True
                messages.add_message(
                    request,
                    messages.ERROR,
                    "Your ownership claim could not be verified as the old "
                    "claim is still in place."
                )

    else:
        messages.add_message(
            request,
            messages.INFO,
            "You need to be logged in to do that."
        )
    return HttpResponseRedirect(
        reverse("servers:server_verify", args=(server_id, ))
    )
