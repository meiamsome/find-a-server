from datetime import datetime, timedelta

from django.core.management.base import BaseCommand
from django.db import connection
from django.db.models import Max, Sum, F, FloatField

from servers.models import Server, UpTime, UpTimeAggregate

TIME_STEP = 30 * 60


class Command(BaseCommand):
    help = "Updates the servers' uptime aggregates"

    def handle(self, *args, **options):
        last = UpTimeAggregate.objects.order_by('checkTime').last()
        if last is None:
            last = datetime.now() - timedelta(hours=24)
        else:
            last = last.checkTime + timedelta(seconds=TIME_STEP)
        now = int(datetime.now().strftime("%s"))
        last = TIME_STEP * (int(last.strftime("%s")) / TIME_STEP)
        start_date = datetime.fromtimestamp(last - TIME_STEP)
        UpTime.objects.filter(checkTime__lte=start_date).delete()
        for end_time in range(last, now, TIME_STEP):
            end_date = datetime.fromtimestamp(end_time)
            start_date = end_date - timedelta(seconds=TIME_STEP)
            storage = []
            for server in Server.objects.filter(
                    uptime__checkTime__range=(start_date, end_date)
            ).annotate(
                player_count=Max('uptime__playerCount'),
                total_time=Sum('uptime__delta'),
                up_time=Sum(
                    F('uptime__delta') * F('uptime__status'),
                    output_field=FloatField())
            ).values('id', 'up_time', 'total_time', 'player_count'):
                storage.append(UpTimeAggregate(
                    server_id=server['id'],
                    checkTime=end_date,
                    playerCount=server['player_count'],
                    up_time=server['up_time'],
                    total_time=server['total_time']
                ))
            UpTimeAggregate.objects.bulk_create(storage)
