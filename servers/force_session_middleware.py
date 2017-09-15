class ForceSessionMiddleware:
    def process_request(self, request):
        if hasattr(request, 'session') and not request.session.session_key:
            request.session.save()
            request.session.modified = True
