"""These services are part of the Akara regression test suite

They test functionality from the akara.services modules
"""

from amara import tree

from akara.services import *
from akara import request, response

## These are all errors in the simple_service definition.
# They are caught in the server. Do them now because any
# failures means the other services will not be registered
try:
    # Slashes are not (yet) allowed in the path
    @simple_service("GET", "http://example.com/test_args", path="simple_service.with/slashes")
    def spam():
        pass
    raise AssertionError("simple_service.with/slashes was allowed")
except ValueError, err:
    assert "may not contain a '/'" in str(err), err


try:
    # Can only "GET" and "POST" in a simple service
    @simple_service("DELETE", "http://example.com/test_args")
    def spam():
        pass
    raise AssertionError("DELETE was allowed")
except ValueError, err:
    assert "only supports GET and POST methods" in str(err), err

try:
    # Slashes are not (yet) allowed in the path
    @service("http://example.com/test_arg", path="service.with/slashes")
    def spam():
        pass
    raise AssertionError("service.with/slashes was allowed")
except ValueError, err:
    assert "may not contain a '/'" in str(err), err

try:
    # Slashes are not (yet) allowed in the path
    @method_dispatcher("http://example.come/mulimethod", "method_dispatcher.with/slashes")
    def spam():
        pass
    raise AssertionError("method_dispatcher.with/slashes was allowed")
except ValueError, err:
    assert "may not contain a '/'" in str(err), err


## These services are called by the test script

# Make sure the environment is set up
@simple_service("GET", "http://example.com/test")
def test_environment():
    # Every extension module has an extra 'AKARA' global module variable
    assert AKARA.config is not None
    assert AKARA.module_name == __name__
    assert isinstance(AKARA.module_config, dict)
    assert AKARA.config.has_section("global")

    # simple services can access the WSGI environ this way
    assert request.environ is not None

    # Here's how to override the response fields
    assert response.code.startswith("200 ")
    assert response.headers == []
    return "Good!"

# Make sure the simple_service can specify the path
# (If not given, uses the function's name)
@simple_service("GET", "http://example.com/test", path="test.new.path")
def test_set_path():
    return "Goody!"

# Return a different content-type
@simple_service("GET", "http://example.com/test", content_type="image/gif")
def test_image_gif():
    # A small gif, from http://www.perlmonks.org/?node_id=7974
    # 1x1 pixel red image
    return ('GIF89a\x01\x00\x01\x00\x90\x00\x00\xff\x00\x00\x00'
            '\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02'
            '\x02\x04\x01\x00;')

# Set the content-type through the response
# Make sure it overrides the one in the simple_service
@simple_service("GET", "http://example.com/test", content_type="image/gif")
def test_dynamic_content_type():
    response.add_header("Content-Type", "chemical/x-daylight-smiles")
    return "c1ccccc1O" # a phenol

# Unicode tests

@simple_service("GET", "http://example.com/test")
def test_unicode_utf8():
    # A simple Unicode string (nothing outside of Latin-1)
    return u"\xc5sa bor i G\xf6teborg"

# Yes, I know I'm not returning text/plain, but I want to make sure
# the simple_service parameter overrides the default, which is based
# on the return being a Unicode string.
@simple_service("GET", "http://example.com/test", "test_unicode_latin1",
                "text/plain", "latin1")
def test_unicode_latin1():
    return u"\xc5sa bor i G\xf6teborg"

# Check that I can override the default content-type specification
@simple_service("GET", "http://example.com/test", None, "text/plain", encoding="utf16")
def test_unicode_utf16():
    response.add_header("Content-Type", "something/strange")
    return u"\xc5sa bor i G\xf6teborg"

# Amara strings
test_document = tree.entity()
node = test_document.xml_append(tree.element(None, "nothing"))
node.xml_attributes["name"] = u"\xc5sa"
node.xml_attributes["city"] = u"G\xf6teborg"
node.xml_append(tree.element(None, "something"))
del node


@simple_service("GET", "http://example.com/test")
def test_xml_utf8():
    return test_document

@simple_service("GET", "http://example.com/test", encoding="latin1")
def test_xml_latin1():
    return test_document

@simple_service("GET", "http://example.com/test", writer="xml-indent")
def test_xml_utf8_indent():
    return test_document

# The default WSGI return types are list of (byte) strings and
# iterator of byte strings. Akara can't do much with these. It assumes
# the results are "text/plain" (if not given) and leave it be.

@simple_service("GET", "http://example.com/test")
def test_list_of_strings():
    return ["This ", "is ", "a ", "test.\n"]

@simple_service("GET", "http://example.com/test")
def test_iterator():
    yield "When shall we three meet again?\n"
    yield "In thunder, lightning, or in rain?\n"
    yield "When the hurlyburly's done,\n"
    yield "When the battle's lost and won.\n"


# Basic args (repeats are not allowed)
@simple_service("GET", "http://example.com/test_args", None, "text/plain")
def test_args(a, b=3):
    return "Hi %s and %s" % (a, b)

# Allow repeated parameters
@simple_service("GET", "http://example.com/test_args", content_type="text/plain",
                allow_repeated_args=True)
def test_repeated_args(a, b=3):
    return "Hello %s and %s" % (a, b)


# Add new headers to the response, including multiple headers with the same name.
@simple_service("GET", "http://example.com/test_args")
def test_add_headers():
    response.add_header("URL", "http://www.xml3k.org/")
    response.add_header("URL", "http://dalkescientific.com/")
    response.add_header("Location", "http://freemix.it/")
    return "Nothing to see here. Move along.\n"

###

@simple_service("GET", "http://example.com/test_echo")
def test_echo_simple_get(**kwargs):
    "This echos a GET request, including the QUERY_STRING"
    for k, v in sorted(kwargs.items()):
        yield "%r -> %r\n" % (k, v)

@simple_service("POST", "http://example.com/test_echo")
def test_echo_simple_post(query_body, query_content_type, **kwargs):
    "This echos a POST request, including the query body"
    yield "Content-Type: %r\n" % query_content_type
    yield "Length: %s\n" % len(query_body)
    yield "Body:\n"
    yield repr(query_body) + "\n"

#### '@service' tests

# the 'service' decorator is a thin wrapper over the standard WSGI
# interface Based on code inpection, just about everything is tested
# by the simple_service decorator, so I'm not going to test all the
# error cases.

@service("http://example.com/test_service")
def test_service_no_path(environ, start_response):
    start_response("200 Ok", [("Content-Type", "text/plain")])
    return "this uses the default path\n"

@service("http://example.com/test_service", "test_service_path")
def test_service_with_a_path(environ, start_response):
    start_response("200 Ok", [("Content-Type", "text/fancy")])
    return "this specified a path\n"

#### @method_dispatcher tests

@method_dispatcher("http://example.come/multimethod")
def test_dispatching_with_no_methods():
    "Test method dispatching"


@method_dispatcher("http://example.come/multimethod", path="test_dispatching_get")
def test_dispatching_but_with_a_different_name():
    pass

@test_dispatching_but_with_a_different_name.simple_method("GET")
def say_hi(a="world"):
    return "Hi, " + a + "!"




   # For now require all methods to match /[A-Z]+/ in a service
