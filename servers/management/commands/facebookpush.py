from datetime import datetime, timedelta

from django.core.management.base import BaseCommand
from django.core.exceptions import ObjectDoesNotExist
from django.utils.timezone import utc

from servers.models import PlayTime, FacebookSync

from open_facebook.api import OpenFacebook


class Command(BaseCommand):
    def handle(self, *args, **options):
        now = datetime.utcnow().replace(tzinfo=utc)
        start = now - timedelta(minutes=20)
        # Mark as ended
        end_mark = now - timedelta(minutes=10)
        not_ended_end = now + timedelta(minutes=10)
        to_be_set = PlayTime.objects.filter(
            minecraft_account__owner__facebook_id__isnull=False,
            end_time__gt=start
        ).select_related('facebooksync')
        facebooks_by_user = {}
        for playtime in to_be_set:
            has_sync = False
            try:
                user = playtime.facebooksync.user
                has_sync = True
            except ObjectDoesNotExist:
                user = playtime.minecraft_account.owner
            facebook = None
            try:
                facebook = facebooks_by_user[user]
            except KeyError:
                facebook = OpenFacebook(user.access_token)
                facebooks_by_user[user] = facebook
            if has_sync:
                if playtime.end_time < end_mark:
                    facebook.set(
                        playtime.facebooksync.fb_id,
                        minecraft_server="https://find-a-server.com{}".format(
                            playtime.server.get_absolute_url()
                        ),
                        start_time=playtime.start_time,
                        end_time=playtime.end_time
                    )
                else:
                    facebook.set(
                        playtime.facebooksync.fb_id,
                        minecraft_server="https://find-a-server.com{}".format(
                            playtime.server.get_absolute_url()
                        ),
                        start_time=playtime.start_time,
                        end_time=not_ended_end
                    )
            else:
                if playtime.end_time < end_mark:
                    fb_id = facebook.set(
                        'me/find-a-server:play',
                        minecraft_server="https://find-a-server.com{}".format(
                            playtime.server.get_absolute_url()
                        ),
                        start_time=playtime.start_time,
                        end_time=playtime.end_time
                    )
                else:
                    fb_id = facebook.set(
                        'me/find-a-server:play',
                        minecraft_server="https://find-a-server.com{}".format(
                            playtime.server.get_absolute_url()
                        ),
                        start_time=playtime.start_time,
                        end_time=not_ended_end
                    )
                fb_id = fb_id['id']
                FacebookSync(playtime=playtime, fb_id=fb_id, user=user).save()
