import os
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

    def __init__(self, server, config):
        self.log = server.log
        self.module_dir = config.get('global', 'ModuleDir')
        self.module_dir = os.path.join(server.server_root, self.module_dir)
        try:
            paths = os.listdir(self.module_dir)
        except OSError, e:
            self.log.info("could not list ModuleDir '%s': %s (errno=%d)",
                          self.module_dir, e.strerror, e.errno)
        else:
            self.log.debug("loading modules from '%s'", self.module_dir)
            for path in paths:
                name, ext = os.path.splitext(path)
                if ext != '.py':
                    continue
                module_config = {}
                if config.has_section(name):
                    module_config.update(config.items(name))
                # Start with a clean slate each time to prevent
                # namespace corruption.
                module_globals = {
                    '__builtins__': __builtins__,
                    '__AKARA_REGISTER_SERVICE__': self._register_service,
                    'AKARA_MODULE_CONFIG': module_config,
                    }
                filename = os.path.join(self.module_dir, path)
                self.log.debug('loading %r', filename)
                execfile(filename, module_globals)
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
