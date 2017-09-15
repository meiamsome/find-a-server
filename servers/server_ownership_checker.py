import dns.resolver

from models import ServerVerificationKey as SVK
from minecraft.client import fake_client


def challenge_ownership(server, challenger):
    old_valid = None
    new_valid = None
    original = server.verification
    dns_check = challenger.verification_mode == SVK.DNS_METHOD
    motd_check = challenger.verification_mode == SVK.MOTD_METHOD
    if original:
        if not dns_check:
            dns_check = original.verification_mode == SVK.DNS_METHOD
        if not motd_check:
            motd_check = original.verification_mode == SVK.MOTD_METHOD
    dns_list = None
    motd = None
    if dns_check:
        try:
            dns_list = [
                x.to_text()[1:-1]
                for x in dns.resolver.query(server.address, 'TXT')
            ]
        except:
            pass
        else:
            if challenger.verification_mode == SVK.DNS_METHOD:
                for value in dns_list:
                    if value == "find-a-server-verification=" + \
                            challenger.verification_code:
                        new_valid = True
                        break
                else:
                    new_valid = False
                    return old_valid, new_valid, dns_list, motd
            if original and original.verification_mode == SVK.DNS_METHOD:
                for value in dns_list:
                    if value == "find-a-server-verification=" + \
                            original.verification_code:
                        old_valid = True
                        break
                else:
                    old_valid = False
    if old_valid or (old_valid is None and new_valid is True):
        return old_valid, new_valid, dns_list, motd
    if motd_check:
        try:
            query = fake_client.query(
                (server.address, int(server.port)),
                timeout=3,
                cascade=False
            )
            try:
                motd = query['description']
                if str(motd) != motd:
                    motd = motd['text']
            except KeyError:
                pass
            else:
                if challenger.verification_mode == SVK.MOTD_METHOD:
                    new_valid = challenger.verification_code in motd
                if original.verification_mode == SVK.MOTD_METHOD:
                    old_valid = original.verification_code in motd
        except:
            pass
    return old_valid, new_valid, dns_list, motd
