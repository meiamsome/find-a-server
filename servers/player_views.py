from django.contrib import messages
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect, HttpResponsePermanentRedirect, \
    Http404
from django.shortcuts import render

from servers import user_requester
from servers.models import Names, MinecraftAccount
from servers.forms import PlayerHistoryForm


def player_list(request):
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
            return HttpResponsePermanentRedirect(
                reverse('servers:player_list')
            )
    pages = Paginator(MinecraftAccount.objects.filter().order_by("id"), 24)
    try:
        page = pages.page(page_num)
    except (EmptyPage, PageNotAnInteger):
        raise Http404
    cann = reverse('servers:player_list')
    if page.number != 1:
        cann += "?page=" + str(page.number)
    return render(request, 'players/list.html', {
        'page': page,
        'canonical': cann,
    })


def find_player(request, username=None):
    if username is None:
        context = {}
        if request.POST:
            form = PlayerHistoryForm(request.POST)
            if form.is_valid():
                if Names.objects.filter(
                        name__iexact=form.cleaned_data['username']):
                    return HttpResponseRedirect(reverse(
                        'servers:find_player',
                        args=(
                            form.cleaned_data['username'],
                        )
                    ))
                elif 'add_if_not_exist' in form.cleaned_data and \
                        form.cleaned_data['add_if_not_exist'] == \
                        form.cleaned_data['username']:
                    try:
                        users = user_requester.request([
                            form.cleaned_data['username']
                        ])
                    except:
                        messages.add_message(
                            request,
                            messages.ERROR,
                            "Could not query Mojang for that username."
                        )
                        raise
                    else:
                        if len(users) == 1:
                            return HttpResponseRedirect(reverse(
                                'servers:find_player',
                                args=(
                                    users.values()[0].name,
                                )
                            ))
                        else:
                            messages.add_message(
                                request,
                                messages.ERROR,
                                "No user with that username could be added."
                                " Is it a real account?")
                            form.cleaned_data.pop('add_if_not_exist', None)
                            form = PlayerHistoryForm(form.cleaned_data)
                else:
                    suggestions = []
                    like = Names.objects.filter(
                        name__icontains=form.cleaned_data['username']
                    ).extra(
                        select={
                            'current': 'end IS NULL',
                        },
                        order_by=[
                            '-current',
                            '-end',
                        ],
                    )[:20]
                    for name in like:
                        for other_name in suggestions:
                            if name.name.lower() == other_name.name.lower():
                                break
                        else:
                            suggestions.append(name)
                        if len(suggestions) > 24:
                            break
                    if suggestions:
                        context['suggestions'] = suggestions
                    messages.add_message(
                        request,
                        messages.ERROR,
                        "No user with that username has yet to be tracked."
                        " Press find again to attempt to add this username."
                    )
                    form.cleaned_data['add_if_not_exist'] = \
                        form.cleaned_data['username']
                    form = PlayerHistoryForm(form.cleaned_data)
        else:
            form = PlayerHistoryForm()
        context['form'] = form
        return render(request, 'players/history-form.html', context)
    holders = Names.objects.filter(name__iexact=username).extra(
        select={
            'current': 'end IS NULL',
        },
        order_by=[
            '-current',
            '-end',
        ], )
    if not holders:
        request.POST = {'username': username, }
        return find_player(request)

    current_holder = None
    try:
        current_holder = MinecraftAccount.objects.get(name__iexact=username)
    except MinecraftAccount.DoesNotExist:
        pass
    if current_holder:
        if len(holders) == 1:
            return HttpResponseRedirect(current_holder.get_absolute_url())
        if current_holder.name != username:
            return HttpResponseRedirect(reverse('servers:find_player', args=(
                current_holder.name,
            )))
    else:
        if holders[0].name != username:
            return HttpResponseRedirect(reverse('servers:find_player', args=(
                holders[0].name,
            )))
    return render(request, "players/history-by-username.html", {
        'username': username,
        'current_holder': current_holder,
        'holders': holders,
    })


def recent_name_changes(request):
    changes = Names.objects.filter(end__isnull=False).select_related(
        'minecraft_account'
    ).order_by('-end')
    return render(request, "players/recent-name-changes.html", {
        'changes': changes[:20],
    })
