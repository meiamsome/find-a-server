from time import sleep
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand

from servers.models import Vote, ExtraServerData
from votifier import votifier


class Command(BaseCommand):
    def __init__(self):
        BaseCommand.__init__(self)
        self.server_by_id = {}

    def get_server(self, server_id):
        if server_id in self.server_by_id:
            return self.server_by_id[server_id]
        data = ExtraServerData.objects.select_related('server').get(
            server_id=server_id,
            type=ExtraServerData.VOTIFIER
        )
        if not data:
            self.server_by_id[server_id] = None
            return None
        port = int(data.content[:5])
        key = data.content[5:]
        data.server.votifier_key = "\n".join((
            "-----BEGIN PUBLIC KEY-----",
            key,
            "-----END PUBLIC KEY-----",
        ))
        data.server.votifier_port = port
        self.server_by_id[server_id] = data.server
        return data.server

    def handle(self, *args, **options):
        # l = logging.getLogger('django.db.backends')
        # l.setLevel(logging.DEBUG)
        # l.addHandler(logging.StreamHandler())
        end = datetime.now() + timedelta(minutes=55)
        while datetime.now() < end:
            for vote in Vote.objects.select_related(
                    'minecraft_account').filter(submitted=False):
                try:
                    server = self.get_server(vote.server_id)
                    votifier.vote(
                        (server.address, server.votifier_port),
                        server.votifier_key,
                        "Find-A-Server.com",
                        vote.minecraft_name,
                        vote.ip,
                        vote.time.strftime("%s")
                    )
                except ExtraServerData.DoesNotExist:
                    pass
                except Exception as e:
                    pass
                    # print("Exception occurred!", e);
                    #TODO
                else:
                    vote.submitted = True
                    vote.save(update_fields=['submitted'])
            sleep(5)
