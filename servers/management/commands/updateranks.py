from django.core.management.base import BaseCommand
from django.db import connection

from servers.models import Server


class Command(BaseCommand):
    help = "Updates the servers' ranks"

    def handle(self, *args, **options):
        connection.cursor().execute(
            "SET @var := 0; UPDATE "
            "%s SET rank = @var := @var + 1 ORDER BY %s DESC;" % (
                Server._meta.db_table,
                Server._meta.get_field('score').column
            )
        )
