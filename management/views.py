from datetime import datetime, timedelta

from Crypto.PublicKey import RSA

from django import forms
from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse
from django.db import connection
from django.db.models import Sum
from django.http import HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import render, get_object_or_404
from django.utils.timezone import utc

from servers.helpers import top_players_by_time
from servers.models import Server, QueryError, Vote, PlayTime, ExtraServerData


class UpdateServerDetailsForm(forms.ModelForm):
    votifier_key = forms.CharField(widget=forms.Textarea, required=False)
    votifier_port = forms.IntegerField(
        max_value=65535,
        min_value=1,
        required=False
    )

    def clean_votifier_port(self):
        port = int(self.cleaned_data['votifier_port'])
        if 0 < port < 65536:
            return port
        raise forms.ValidationError("Votifier port is invalid.")

    def clean_votifier_key(self):
        key = str(self.cleaned_data['votifier_key'].strip())
        if not key:
            return
        votifier_key = "\n".join([
            "-----BEGIN PUBLIC KEY-----",
            key,
            "-----END PUBLIC KEY-----",
        ])
        try:
            RSA.importKey(str(votifier_key))
        except Exception as _:
            raise forms.ValidationError(
                "Votifier key is not a valid RSA public key."
            )
        return key

    def save(self, commit=True):
        server = forms.ModelForm.save(self, commit)
        if commit:
            current = ExtraServerData.objects.filter(
                server=server,
                type=ExtraServerData.VOTIFIER
            ).first()
            key = self.cleaned_data['votifier_key']
            if not key:
                if current:
                    current.delete()
            else:
                stored = str(self.cleaned_data['votifier_port']).zfill(5) + key
                if current:
                    current.content = stored
                    current.save()
                else:
                    ExtraServerData(
                        server=server,
                        type=ExtraServerData.VOTIFIER,
                        content=stored
                    ).save()
        return server

    def __init__(self, *args, **kwargs):
        super(UpdateServerDetailsForm, self).__init__(*args, **kwargs)
        if 'instance' in kwargs:
            votifier = ExtraServerData.objects.filter(
                server=kwargs['instance'],
                type=ExtraServerData.VOTIFIER
            ).first()
            if votifier:
                port = int(votifier.content[:5])
                key = votifier.content[5:]
                self.fields['votifier_port'].initial = port
                self.fields['votifier_key'].initial = key

    class Meta:
        model = Server
        fields = ['name']


@login_required
def manage_server(request, server_id):
    server = get_object_or_404(Server, pk=server_id)
    if server.owner != request.user and not request.user.is_staff:
        return HttpResponseForbidden()
    if request.method == "POST":
        form = UpdateServerDetailsForm(request.POST, instance=server)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(
                reverse('management:server', args=[server.id])
            )
    else:
        form = UpdateServerDetailsForm(instance=server)
    now = datetime.utcnow().replace(tzinfo=utc)
    scores = [
        {
            'name': 'Votes',
            'how': 'You receive 1000 points for every vote for your server '
                   'in the past week.',
            'number': 1000 * Vote.objects.filter(
                time__gt=now - timedelta(weeks=1),
                server=server
            ).count(),
        },
        {
            'name': 'Playtime',
            'how': 'You receive 1 point for every minute played in the last '
                   'week. This only works if you have the full query enabled.',
            'number': PlayTime.objects.filter(
                end_time__gt=now - timedelta(weeks=1),
                server=server
            ).aggregate(Sum('duration'))['duration__sum'],
        },
        {
            'name': 'Unique Players',
            'how': 'You get 10 points for every unique player in the past '
                   'week. This only works if you have the full query enabled.',
            'number': 10 * top_players_by_time(
                server_id,
                date_min=now - timedelta(weeks=1)
            ).count(),
        },
    ]
    # Aggregate playtime can be none if there are no results.
    if scores[1]['number'] is None:
        scores[1]['number'] = 0
    # Converts seconds to minutes
    scores[1]['number'] /= 60

    # Calculate the uptime percentage.
    cursor = connection.cursor()
    cursor.execute(
        "SELECT SUM(`up_time`) as up, SUM(`total_time`) as total FROM "
        "`servers_uptimeaggregate` WHERE checkTime > NOW() - INTERVAL "
        "1 WEEK AND server_id = %s ", [server_id])
    row = cursor.fetchone()
    # If we have results, and some time was checked
    if row and row[1] and int(row[1]) != 0:
        uptime = (100 * float(row[0]) / float(row[1]))
    else:
        uptime = 0
    # Detect if votifier exists
    if ExtraServerData.objects.filter(
            server=server,
            type=ExtraServerData.VOTIFIER
    ).exists():
        votifier = 1.5
    else:
        votifier = 1
    # Number of votes not submitted yet
    outstanding = Vote.objects.filter(server=server, submitted=False).count()
    if outstanding > 2:
        votifier = min(1, votifier - (outstanding - 2)/20)
    multipliers = [
        {
            'name': 'Votifier Bonus',
            'how': 'You receive a 1.5x multiplier for having votifier enabled '
                   'on your server. This multiplier is reduced if votes '
                   'cannot be submitted to your server.',
            'number': votifier,
        },
        {
            'name': 'Uptime Bonus',
            'how': 'Get up to a 2x bonus depending on the uptime of your '
                   'server in the past week.',
            'number': (100 + uptime)/float(100),
        },
    ]
    # Add warning for outstanding votes
    if outstanding > 2:
        multipliers[0]['how'] += '<br /><span style="color:red">' +\
            'You have %i outstanding votes</span>' % outstanding
    for multi in multipliers:
        multi['format'] = "%.2f" % multi['number']
    pre_score = sum(x['number'] for x in scores)
    total_multiplier = reduce(
        lambda x, y: x * y,
        (x['number'] for x in multipliers)
    )
    score = int(pre_score * total_multiplier)
    if server.score != score:
        server.score = score
        server.save(update_fields=['score'])
    return render(request, 'management/server.html', {
        'server': server,
        'server_scores': scores,
        'total_score_pre': pre_score,
        'server_multipliers': multipliers,
        'total_multiplier': "%.2f" % total_multiplier,
        'score': score,
        'errors': QueryError.objects.filter(
            server=server
        ).order_by('-time')[0:10],
        'form': form,
    })
