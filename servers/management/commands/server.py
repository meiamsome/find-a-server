import socket

from django.core.management.base import BaseCommand

from minecraft.server import fake_server


class Command(BaseCommand):
    help = "Runs the verification server."

    def handle(self, *args, **options):
        try:
            fake_server.run_server(("find-a-server.com", 25565))
        except socket.error as err:
            if err.errno != 98:
                raise
