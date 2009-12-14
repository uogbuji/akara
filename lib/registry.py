"""Service registry

Add WSGI handlers to the Akara HTTP dispatch registry.

"""

import inspect

from amara import tree

from akara import logger

__all__ = ("register_service", "get_service")

#### Simple registry of services


# We had some discussion about using the term 'path' or 'mount_point'?
# Right now we don't really have '/' paths so there's no real difference
# Therefore, you register mount_points, which must not have a "/" in them.
# Incoming requests have a path, and the first segment (before the "/")
# is used to find the mount point.

# We're calling it a 'path' for future compatibility.  For more
# complex paths we might want to use Routes or similar system, in
# which case we'll also have pattern matching on the path segments.
# You'll likely register a path pattern, still with the name 'path'.

class Service(object):
    "Internal class to store information about a given service resource"
    def __init__(self, handler, path, ident, doc):
        self.handler = handler # most important - the function to call
        # XXX is it okay for the path to be None? I think so ...
        self.path = path  # where to find the service
        self.ident = ident  # URN which identifies this uniquely
        self.doc = doc  # description to use when listing the service

class Registry(object):
    "Internal class to handle resource registration information"
    def __init__(self):
        self._registered_services = {}

    def register_service(self, ident, path, handler, doc=None):
        if "/" in path:
            raise ValueError("Registered path %r may not contain a '/'" % (path,))
        if doc is None:
            doc = inspect.getdoc(handler) or ""
        if ident in self._registered_services:
            logger.warn("Replacing mount point %r (%r)" % (path, ident))
        else:
            logger.debug("Created new mount point %r (%r)" % (path, ident))
        serv = Service(handler, path, ident, doc)
        self._registered_services[path] = serv

    def get_service(self, path):
        return self._registered_services[path]

    def list_services(self, ident=None):
        document = tree.entity()
        services = document.xml_append(tree.element(None, 'services'))
        for path, service in sorted(self._registered_services.iteritems()):
            if ident is not None and service.ident != ident:
                continue
            service_node = services.xml_append(tree.element(None, 'service'))
            service_node.xml_attributes['ident'] = service.ident
            E = service_node.xml_append(tree.element(None, 'path'))
            E.xml_append(tree.text(path))
            E = service_node.xml_append(tree.element(None, 'description'))
            E.xml_append(tree.text(service.doc))
        return document

_current_registry = Registry()


def register_service(ident, path, function, doc=None):
    _current_registry.register_service(ident, path, function, doc)

def get_service(mount_point):
    return _current_registry.get_service(mount_point)

def list_services(ident=None):
    return _current_registry.list_services(ident)

def get_a_service_by_id(ident):
    for path, service in _current_registry._registered_services.items():
        if service.ident == ident:
            return service
    return None

import urllib
from cStringIO import StringIO

def _flatten_kwargs(kwargs):
    data = []
    for k,v in kwargs.items():
        if isinstance(v, basestring):
            data.append( (k, v) )
        else:
            for item in v:
                data.append( (k, item) )
    return data

def _build_query_string(query_args, kwargs):
    if query_args is None:
        if kwargs is None:
            return ""
        # all kwargs MUST be url-encodable
        return urllib.urlencode(_flatten_kwargs(kwargs))

    if kwargs is None:
        # query_args MUST be url-encodable
        return urllib.urlencode(query_args)
    raise TypeError("Cannot specify both 'query_args' and keyward arguments")
    

class Stage(object):
    def __init__(self, ident, query_args=None, **kwargs):
        self.ident = ident
        self.query_string = _build_query_string(query_args, kwargs)
    def __repr__(self):
        return "Stage(%r, %r)" % (self.ident, self.query_string)

def _flag_position(data):
    first_flags = [1] + [0] * (len(data)-1)
    last_flags = first_flags[::-1]
    return zip(first_flags, last_flags, data)
        

class Pipeline(object):
    def __init__(self, ident, path, stages, doc):
        assert len(stages) > 0, "XXX"
        self.ident = ident
        self.path = path
        self.stages = stages
        self.doc = doc

    def __call__(self, environ, start_response):
        print "In the call"
        captured_response = []
        captured_body = StringIO()
        captured_body_length = None

        def capture_start_response(status, headers, exc_info=None):
            captured_response[:] = [status, headers, exc_info]
        def _find_header(search_term):
            search_term = search_term.lower()
            for (name, value) in captured_response[1]:
                if name.lower() == search_term:
                    return value
            raise AssertionError("Could not find XXX")

        for is_first, is_last, stage in _flag_position(self.stages):
            print "Checking", is_first, is_last, stage
            stage_environ = environ.copy()
            if not is_first:
                stage_environ["REQUEST_METHOD"] = "POST"
            stage_environ["SCRIPT_NAME"] = "spam"
            stage_environ["PATH_INFO"] = "blah"
            if is_first:
                if stage.query_string:
                    if stage_environ["QUERY_STRING"]:
                        stage_environ["QUERY_STRING"] += ("&" + stage.query_string)
                    else:
                        stage_environ["QUERY_STRING"] = stage.query_string
            else:
                if stage.query_string:
                    stage_environ["QUERY_STRING"] = stage.query_string
                else:
                    stage_environ["QUERY_STRING"] = ""

            if not is_first:
                stage_environ["CONTENT_TYPE"] = _find_header("content-type")
                stage_environ["CONTENT_LENGTH"] = captured_body_length
                stage_environ["wsgi.input"] = captured_body

            service = get_a_service_by_id(stage.ident)

            if is_last:
                return service.handler(stage_environ, start_response)
            else:
                captured_body.seek(0)
                captured_body.truncate()
                result = service.handler(stage_environ, capture_start_response)
                try:
                    # Support wsgi.file_wrapper?
                    for chunk in result:
                        captured_body.write(chunk)
                finally:
                    if hasattr(result, "close"):
                        result.close()
                captured_body_length = captured_body.tell()
                captured_body.seek(0)
        raise AssertionErorr("should never get here")

def _normalize_stage(stage):
    if isinstance(stage, basestring):
        return Stage(stage)
    return stage

def register_pipeline(ident, path=None, stages=None, doc=None):
    if not stages:
        raise TypeError("a pipeline must have stages")
    stages = [_normalize_stage(stage) for stage in stages]

    # Check that the stages exist?

    pipeline = Pipeline(ident, path, stages, doc)
    register_service(ident, path, pipeline, doc)
    
