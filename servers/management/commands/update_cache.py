from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.core.urlresolvers import reverse
from django.http import HttpRequest

from servers.views import player_list_no_cache, statistics_no_cache


# Updates the cached players and server pages.
class Command(BaseCommand):

    def handle(self, *args, **options):
        to_update = dict()
        # Players page
        request = HttpRequest()
        request.path = reverse("servers:players", args=args)
        cache_key = "player_list"
        to_update[cache_key] = player_list_no_cache(request)

        # Stats page
        request.path = reverse("servers:stats", args=args)
        cache_key = "statistics"
        to_update[cache_key] = statistics_no_cache(request)
        cache.set_many(to_update, timeout=60*60)
