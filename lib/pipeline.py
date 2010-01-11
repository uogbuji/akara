"""Support code for building service pipelines

A pipeline is a collection of stages. Each stage corresponds to a
service, which takes the input, processes it, and produces output.

The first stage uses the incoming HTTP request as input, and the
output from the last stage produces the HTTP response. All of the
stages follow the WSGI specification. The pipeline knows how to
convert the WSGI response into the successive WSGI query.

"""

__all__ = ["Pipeline", "Stage", "register_pipeline"]

import urllib
from cStringIO import StringIO

from akara import logger
from akara import registry

# Helper function to figure out which stage is the first and/or last stage
#  [X] -> [ (1,1,X])
#  [X, Y] -> [ (1,0,X), (0,1,Y) ]
#  [X, Y, Z] -> [ (1,0,X), (0,0,Y), (0,1,Z) ]
def _flag_position(data):
    first_flags = [1] + [0] * (len(data)-1)
    last_flags = first_flags[::-1]
    return zip(range(len(data)), first_flags, last_flags, data)

def _find_header(search_term, headers):
    search_term = search_term.lower()
    for (name, value) in headers:
        if name.lower() == search_term:
            return value
    raise AssertionError("Could not find %r in the headers" % search_term)


class Pipeline(object):
    def __init__(self, ident, path, stages, doc):
        if not len(stages):
            raise TypeError("No stages defined for the pipeline")
        self.ident = ident
        self.path = path
        self.stages = stages
        self.doc = doc

    def __call__(self, environ, start_response):
        # The WSGI entry point for the pipeline
        
        logger.debug("Started the %s (%s) pipeline", self.ident, self.path)

        # Help capture the response of a WSGI request,
        # so I can forward it as input to the next request.
        captured_response = [None, None, None]
        captured_body_length = None
        def capture_start_response(status, headers, exc_info=None):
            if exc_info is None:
                captured_response[:] = [status, headers, False]
            else:
                captured_response[:] = [status, headers, True]
                # Forward this to the real start_response
                return start_response(status, headers, exc_info)

        num_stages = len(self.stages)
        for stage_index, is_first, is_last, stage in _flag_position(self.stages):
            service = registry.get_a_service_by_id(stage.ident)
            if service is None:
                logger.error("Pipeline %r(%r) could not find a %r service",
                              self.ident, self.path, stage.ident)
                start_response("500 Internal server error", [("Content-Type", "text/plain")])
                return ["Broken internal pipeline.\n"]

            # Construct a new environ for each stage in the pipeline.
            # We have to make a new one since a stage is free to
            # do whatever it wants to the environ. (It does not have
            # free reign over all the contents of the environ.)
            stage_environ = environ.copy()
            if not is_first:
                # The first stage gets the HTTP request method
                # Everything else gets a POST.
                stage_environ["REQUEST_METHOD"] = "POST"
            assert service.path is not None # Can some services/pipelines not be mounted?
            stage_environ["SCRIPT_NAME"] = service.path
            #stage_environ["PATH_INFO"] = ... # I think  this is best left unchanged. XXX

            if is_first:
                # Augment the QUERY_STRING string with any pipeline-defined query string
                # (You probably shouldn't be doing this. Remove this feature? XXX)
                if stage.query_string:
                    if stage_environ["QUERY_STRING"]:
                        stage_environ["QUERY_STRING"] += ("&" + stage.query_string)
                    else:
                        stage_environ["QUERY_STRING"] = stage.query_string
            else:
                # The other stages get nothing about the HTTP query string
                # but may get a pipeline-defined query string
                if stage.query_string:
                    stage_environ["QUERY_STRING"] = stage.query_string
                else:
                    stage_environ["QUERY_STRING"] = ""

            if not is_first:
                # Forward information from the previous stage
                stage_environ["CONTENT_TYPE"] = _find_header("content-type",
                                                             captured_response[1])
                stage_environ["CONTENT_LENGTH"] = captured_body_length
                stage_environ["wsgi.input"] = captured_body

                # Make the previous response headers available to the next stage
                stage_environ["akara.pipeline_headers"] = captured_response[1]

            logger.debug("Pipeline %r(%r) at stage %r (%d/%d)",
                         self.ident, self.path, stage.ident, stage_index+1, num_stages)
            if is_last:
                # End of the pipeline. Let someone else deal with the response
                return service.handler(stage_environ, start_response)
            else:
                # Intermediate stage output. Collect to forward to the next stage
                captured_body = StringIO()
                result = service.handler(stage_environ, capture_start_response)

                # Did start_response get an exc_info term? (It might not
                # have been thrown when forwarded to the real start_response.)
                if captured_response[2]:
                    # It didn't raise an exception. Assume the response contains
                    # the error message. Forward it and stop the pipeline.
                    logger.debug(
                        "Pipeline %r(%r) start_response received exc_info from stage %r. Stopping.",
                        self.ident, self.path, stage.ident)
                    return result

                # Was there some sort of HTTP error?
                status = captured_response[0].split(None, 1)[0]
                # XXX What counts as an error?
                if status not in ("200", "201"):
                    logger.debug(
                        "Pipeline %r(%r) start_response received status %r from stage %r. Stopping.",
                        self.ident, self.path, status, stage.ident)
                    start_response(captured_response[0], captured_response[1])
                    # This should contain error information
                    return result

                # Save the response to the cStringIO
                try:
                    # We might be able to get some better performance using
                    # a wsgi.file_wrapper. If the chunks come from a file-like
                    # object then we can reach in and get that file-like object
                    # instead of copying it to a new one
                    for chunk in result:
                        captured_body.write(chunk)
                finally:
                    # Part of the WSGI spec
                    if hasattr(result, "close"):
                        result.close()
                captured_body_length = captured_body.tell()
                captured_body.seek(0)

        raise AssertionErorr("should never get here")


# The dictionary values may be strings for single-valued arguments, or
# list/tuples for multiple-valued arguments. That is
#   dict(a=1, z=9)      -> "a=1&z=9"
#   dict(a=[1,2, z=9])  -> "a=1&a=2&z=9"
# This function helps flatten the values, producing a tuple-stream
# that urlencode knows how to process.

def _flatten_kwargs_values(kwargs):
    result = []
    if isinstance(kwargs, dict):
        args = kwargs.items()
    else:
        args = kwargs
    for k,v in args:
        if isinstance(v, basestring):
            result.append( (k,v) )
        else:
            for item in v:
                result.append( (k, item) )
    return result

def _build_query_string(query_args, kwargs):
    if query_args is None:
        if kwargs is None or kwargs == {}:
            return ""
        # all kwargs MUST be url-encodable
        return urllib.urlencode(_flatten_kwargs_values(kwargs))

    if kwargs is None or kwargs == {}:
        # query_args MUST be url-encodable
        return urllib.urlencode(_flatten_kwargs_values(query_args))
    raise TypeError("Cannot specify both 'query_args' and keyword arguments")


class Stage(object):
    """Define a stage in the pipeline

    'ident' is the service identifier which uniquely identifies the service
    To specify additional QUERY_STRING arguments passed to the service use one of:

      query_args - a list of (name, value) tuples
      **kwargs - the kwargs.items() are used as (name, value) tuples
      query_string - the raw query string

    If the value is a string then the name, value pair is converted to
    an HTTP query parameter. Otherwise the value is treated as a list
    and each list item adds a new query parameter

            (name, value[0]), (name, value[1]), ...

    Here are examples:
       # Using query_args (which preserves order)
       Stage("http://example.com", [("a", ["1", "2"]), ("b", "9")])
           ->  QUERY_STRING = "a=1&a=2&b=9"

       # Using kwargs (which might not preserve order)
       Stage("http://example.com", a=["1", "2"], b="9")
           ->  QUERY_STRING = "b=9&a=1&a=2"

       # Using a raw query string
       Stage("http://example.com", query_string="a=2&b=9&a=1")
           ->  QUERY_STRING = "a=2&b=9&a=1"
    
    The first stage gets the HTTP request QUERY_STRING plus
    the query string defined for the stage. The other stages
    only get the query string defined for the stage.
    """
    def __init__(self, ident, query_args=None, query_string=None, **kwargs):
        self.ident = ident
        if query_string is not None:
            if query_args is not None:
                raise TypeError("Cannot specify both 'query_string' and 'query_args'")
            if kwargs:
                raise TypeError("Cannot specify both 'query_string' and keyword argument")
            self.query_string = query_string
        else:
            self.query_string = _build_query_string(query_args, kwargs)


def _normalize_stage(stage):
    if isinstance(stage, basestring):
        return Stage(stage)
    return stage

def register_pipeline(ident, path=None, stages=None, doc=None):
    if not stages:
        raise TypeError("a pipeline must have stages")
    stages = [_normalize_stage(stage) for stage in stages]

    # Should I check that the dependent stages are already registered?

    pipeline = Pipeline(ident, path, stages, doc)
    registry.register_service(ident, path, pipeline, doc)
