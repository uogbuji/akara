import os
from wsgiref.simple_server import WSGIRequestHandler
from wsgiref.util import shift_path_info, request_uri

class configdict(dict):

    def __init__(self, server):
        self._server = server

    def server_root_relative(self, path):
        return os.path.join(self._server.server_root, path)


class wsgi_application:

    # Default error message
    error_document_template = """<?xml version="1.0" encoding="ISO-8859-1"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"
  "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
<hmtl xmlns="http://www.w3.org/1999/xhtml" lang="en" xml:lang="en">
<head>
  <title>%(title)s</title>
</head>
<body>
  <h1>%(title)s</h1>
  <p>
  %(body)s
  </p>
  <h2>Error %(code)s</h2>
</body>
</html>
"""

    def __init__(self, server, config):
        self.services = { '': self._list_services }
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
                module_config = configdict(server)
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

    def _list_services(self, environ, start_response):
        template = ('<service name="%s">\n'
                    '  <path>%s</path>\n'
                    '  <description>%s</description>\n'
                    '</service>\n')
        services = []
        for path, func in self.services.iteritems():
            services.append(template % (func.__name__, path, func.__doc__))
        start_response('200 OK', [('Content-Type', 'text/xml')])
        return services

    def __call__(self, environ, start_response):
        """WSGI handler"""
        name = shift_path_info(environ)
        try:
            service = self.services[name]
        except KeyError:
            start_response('404 Not Found', [('Content-Type', 'text/html')])
            code = 404
            status, body = WSGIRequestHandler.responses[code]
            params = {'code': code,
                      'title': status,
                      'body': body,
                      }
            response = [self.error_document_template % params]
        else:
            response = service(environ, start_response)
        return response
