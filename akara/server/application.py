from wsgiref.util import shift_path_info, request_uri

class wsgi_application:

    services = {}

    # Default error message
    error_document_template = """\
<head>
  <title>Error response</title>
</head>
<body>
  <h1>Error response</h1>
  <p>Error code %(code)d.
  <p>Message: %(message)s.
  <p>Error code explanation: %(code)s = %(explain)s.
</body>
"""

    def __init__(self, server, modules):
        self.log = server.log
        for module in modules:
            # Start with a clean slate each time to prevent
            # namespace corruption.
            global_dict = {
                '__builtins__': __builtins__,
                '__AKARA_REGISTER_SERVICE__': self._register_service,
                }
            self.log.debug('loading %r', module)
            execfile(module, global_dict)
        return

    def _register_service(self, func, ident, path):
        self.log.debug('registering %s to %s.%s()', path,
                       func.__module__, func.__name__)
        self.services[path] = func
        return

    def __call__(self, environ, start_response):
        """WSGI handler"""
        name = shift_path_info(environ)
        try:
            service = self.services[name]
        except KeyError:
            start_response('404 Not Found', [('content-type', 'text/html')])
            url = request_uri(environ)
            params = {
                'code': 404,
                'message': 'Not Found',
                'explain': 'The requested URL %s was not found' % url,
                }
            response = [self.error_document_template % params]
        else:
            response = service(environ, start_response)
        return response
