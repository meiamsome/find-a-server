from datetime import datetime, timedelta

from django.db.models import Max
from django.contrib.auth import authenticate, login, get_user_model
from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.shortcuts import render, get_object_or_404
from django.utils.timezone import utc

from servers.models import MinecraftAccount, Server, PlayTime, UpTime, \
    QueryError

from users.forms import RegistrationForm


def register(request):
    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            user2 = authenticate(
                username=user.username,
                password=form.cleaned_data['password']
            )
            login(request, user2)
            return HttpResponseRedirect(reverse("self_view"))
    else:
        form = RegistrationForm()
    # TODO set up the form
    return render(request, 'registration/register.html', {
        'form': form,
    })


@login_required
def self_view(request):
    user = request.user
    now = datetime.utcnow().replace(tzinfo=utc)
    context = {
        'servers': Server.objects.filter(owner=user),
        'mc_accs': MinecraftAccount.objects.filter(owner=user).annotate(
            last_seen=Max("playtime__end_time")
        ).order_by('-last_seen'),
        'now': now,
    }
    for server in context['servers']:
        server.has_error = QueryError.objects.filter(server=server).exists()
        server.full_query = PlayTime.objects.filter(
            server=server,
            end_time__gte=now - timedelta(minutes=5)
        ).exists()
    uptimes = UpTime.objects.filter(
        server__in=context['servers'],
        checkTime__gte=now - timedelta(minutes=5)
    ).annotate(time=Max('checkTime')).order_by('-checkTime')
    for uptime in uptimes:
        for server in context['servers']:
            if uptime.server_id == server.id:
                server.last_up = uptime
    for player in context['mc_accs']:
        if player.last_seen is None:
            player.online = False
        elif now - player.last_seen < timedelta(minutes=5):
            player.online = True
        else:
            player.online = False
    return render(request, 'users/me.html', context)


def user_detail(request, username):
    user = get_object_or_404(get_user_model(), username=username)
    now = datetime.utcnow().replace(tzinfo=utc)
    context = {
        'the_user': user,
        'owned_mc_accounts': MinecraftAccount.objects.filter(
            owner=user
        ).annotate(
            last_seen=Max("playtime__end_time")
        ).order_by('-last_seen'),
        'owned_servers': Server.objects.filter(owner=user),
    }
    uptimes = UpTime.objects.filter(
        server__in=context['owned_servers'],
        checkTime__gte=now - timedelta(minutes=5)
    ).annotate(time=Max('checkTime')).order_by('-checkTime')
    for uptime in uptimes:
        for server in context['owned_servers']:
            if uptime.server_id == server.id:
                server.last_up = uptime
    for server in context['owned_servers']:
        server.full_query = PlayTime.objects.filter(
            server=server,
            end_time__gte=now - timedelta(minutes=5)
        ).exists()
    for player in context['owned_mc_accounts']:
        if player.last_seen is None:
            player.online = False
        elif now - player.last_seen < timedelta(minutes=5):
            player.online = True
        else:
            player.online = False
    data = PlayTime.objects.filter(
        minecraft_account__in=context['owned_mc_accounts'],
        end_time__gte=now - timedelta(weeks=1)
    ).select_related('server__name', 'minecraft_account__name')
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
                        "'%s'" % s.server.name,
                        "'%s'" % s.minecraft_account.name,
                        "new Date(%s)" % (
                            (s.end_time - timedelta(
                                seconds=s.duration + 1
                            )).strftime("%s") + "000"
                        ),
                        "new Date(%s)" % (s.end_time.strftime("%s") + "000"),
                    ) for s in data
                ),
                'options': """{
                    hAxis: {
                        viewWindowMode:'explicit',
                        viewWindow: {
                            min: new Date(%s),
                            max: new Date(%s)
                        }
                    },
                    timeline: {
                        groupByBarLabel: true
                    }
                }""" % (
                    (now - timedelta(weeks=4)).strftime("%s") + "000",
                    now.strftime("%s") + "000"
                ),
            }
        ]
    return render(request, 'users/user_detail.html', context)
