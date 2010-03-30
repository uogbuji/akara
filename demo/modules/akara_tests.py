"""These services are part of the Akara regression test suite

They test functionality from the akara.services modules
"""
import os

from amara import tree, parse

from akara.services import *
from akara.pipeline import *
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

# This exists only to get two hits in the "/" index
@simple_service("GET", "http://example.com/test_echo")
def test_echo_simple_get2(**kwargs):
    "Hi test_server.py!"
    return test_echo_simple_get(**kwargs)

@simple_service("POST", "http://example.com/test_echo_post")
def test_echo_simple_post(query_body, query_content_type, **kwargs):
    "This echos a POST request, including the query body"
    yield "Content-Type: %r\n" % query_content_type
    yield "Length: %s\n" % len(query_body)
    yield "Body:\n"
    yield repr(query_body) + "\n"


@simple_service("POST", "http://echo_request_headers")
def test_echo_post_headers(query_body, ignore):
    from akara import request
    for k, v in request.environ.items():
        if k.startswith("HTTP_"):
            k = k[5:]
            yield "%s -> %s\n" % (k, v)
    yield "== End of the headers ==\n"


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


@method_dispatcher("http://example.com/multimethod", path="test_dispatching_get")
def test_dispatching_but_with_a_different_name():
    pass

@test_dispatching_but_with_a_different_name.simple_method("GET")
def say_hi(a="world"):
    return "Hi, " + a + "!"

@method_dispatcher("http://example.com/multimethod")
def test_multimethod():
    "SHRDLU says 'QWERTY'"


try:
    # Some error testing.
    # Although the HTTP spec allows a wider range of HTTP methods,
    # Akara requires that all methods match /[A-Z]+/
    @test_multimethod.method("lowercase", "text/html")
    def do_post(environ, start_response):
        start_response("202 Accepted", [])
        return ""
    raise AssertionError("Why was a lowercase method allowed?")
except ValueError, err:
    assert "HTTP method 'lowercase' value is not valid. It must contain" in str(err), repr(err)

try:
    # Some more error testing
    @test_multimethod.method("A-Z", "text/html")
    def do_post(environ, start_response):
        start_response("202 Accepted", [])
        return ""
    raise AssertionError("Why was a method with a hyphen allowed?")
except ValueError, err:
    assert "HTTP method 'A-Z' value is not valid. It must contain" in str(err), repr(err)

try:
    # simple only works for GET and POST
    @test_multimethod.simple_method("DELETE")
    def do_delete():
        pass
    raise AssertionError("Why can DELETE be a simple_method?")
except ValueError, err:
    assert "only supports GET and POST methods" in str(err), str(err)
    


# NOTE: if this doesn't work (with a 405 error) then the above error tests
# likely failed, raising an AssertionError. Check the error log
@test_multimethod.simple_method("GET", "text/fancy", allow_repeated_args=True)
def do_get(a, b="spam"):
    return "My name is %r. I like %r" % (a, b)

@test_multimethod.simple_method("POST", "text/schmancy")
def do_post(query_body, query_content_type, a="default value"):
    yield "You sent %d bytes of %r and %r\n" % (len(query_body), query_content_type, a)
    yield "First few bytes: %r\n" % (query_body[:20],)

@test_multimethod.method("DELETE")
def do_delete(environ, start_response):
    if environ.get("CONTENT_TYPE") != "chemical/x-daylight-smiles":
        start_response("501 Not Implemented", [("Content-Type", "text/plain")])
        return "give me a SMILES, not a %s" % environ.get("Content-Type")
    s = environ["wsgi.input"].read(6)
    if s != "[U235]":
        start_response("501 Not Implemented", [("Content-Type", "text/plain")])
        return "Where is the kaboom? There was supposed to be an earth-shattering kaboom!"

    start_response("202 Accepted", [("Content-Type", "application/my-xml")])
    return test_document

@test_multimethod.method("TEAPOT")
def do_extension(environ, start_response):
    start_response("418 I'm a teapot", [("Content-Type", "text/plain")])
    return "short and stout"

#####

@method_dispatcher("http://example.com/multimethod")
def test_dispatch_unicode():
    pass

@test_dispatch_unicode.simple_method("GET", encoding="latin1")
def get_latin1():
    return u"\xc5sa bor i G\xf6teborg"

@test_dispatch_unicode.simple_method("POST", encoding="utf-8")
def post_utf8(body, content_type):
    return u"\xc5sa bor i G\xf6teborg"

@method_dispatcher("http://example.com/multimethod")
def test_dispatch_xml():
    pass


@test_dispatch_xml.simple_method("GET", encoding="utf-8", writer="xml")
def get_xml_utf8():
    return test_document

@test_dispatch_xml.simple_method("POST", encoding="utf-16", writer="xml-indent")
def post_xml_indent_utf16(environ, start_response):
    return test_document



### used in test_server.py
_call_count = 0
@simple_service("GET", "http://example.com/count")
def test_get_call_count():
    global _call_count
    print "Currently", _call_count
    s = "%s %s" % (_call_count, os.getpid())
    _call_count += 1
    return s

#### pipelines

@simple_service("POST", "service:rot13")
def test_rot13(query_body, query_content_type):
    return query_body.encode("rot13")

@simple_service("POST", "service:base64-encode")
def test_base64_encode(query_body, query_content_type):
    return query_body.encode("base64")

@simple_service("POST", "service:base64-decode")
def test_base64_decode(query_body, query_content_type):
    return query_body.decode("base64")

import hashlib

@simple_service("POST", "service:md5-hash")
def test_md5(query_body, query_content_type, key=""):
    x = hashlib.md5(key)
    x.update(query_body)
    return x.digest()


register_pipeline("http://dalkescientific.com/hash_encode",
                  "hash_encode",
                  stages = [Stage("service:md5-hash", key="secret"),
                            "service:base64-encode",
                            ])

# This pipeline depends on another pipeline
register_pipeline("http://dalkescientific.com/hash_encode_rot13",
                  "hash_encode_rot13",
                  stages = ["http://dalkescientific.com/hash_encode",
                            "service:rot13",
                            ])

# This pipeline takes a GET as input
@simple_service("GET", "service:get_name")
def test_repeat_get(text="Andrew"):
    return text

@simple_service("POST", "service:count_children")
def test_count_matches(query_body, query_content_type, xslt="*/*"):
    doc = parse(query_body)
    n = len(doc.xml_select(xslt))
    return str(n)

register_pipeline("http://dalkescientific.com/get_hash",
                  "get_hash",
                  stages = ["service:get_name",
                            "service:md5-hash",
                            "service:base64-encode",
                            ])

register_pipeline("http://dalkescientific.com/broken_pipeline",
                  "broken_pipeline1",
                  stages = ["null:missing:stage",
                            "service:rot13",
                            ])

register_pipeline("http://dalkescientific.com/broken_pipeline",
                  "broken_pipeline2",
                  stages = ["http://dalkescientific.com/hash_encode",
                            "null:missing:stage",
                            ])
register_pipeline("http://dalkescientific.com/count_registry",
                  "test_count_registry",
                  stages = ["http://purl.org/xml3k/akara/services/registry",
                            "service:count_children"])

##### Templates

@simple_service("GET", "urn:akara.test:template-1", path="test.template1",
                query_template = "?name={name}&language={lang?}")
def test_template1(name="Pat", language=None, os="unix"):
    assert language is not None
    assert os == "unix"
    return "%s uses %s on %s" % (name, language, os)

@simple_service("GET", "urn:akara.test:template-2", path="test.template2")
def test_template2(name, language=None, os="unix"):
    assert language is not None
    assert os == "unix"
    return "%s uses %s on %s" % (name, language, os)

@simple_service("POST", "urn:akara.test:template-3")
def test_template3(name="Ant", language=None, os="unix"):
    assert language is not None
    assert os == "unix"
    return "%s uses %s on %s" % (name, language, os)

@simple_service("GET", "urn:akara.test:template-4", path="test.template4")
def test_template4():
    return "Here"


@simple_service("GET", "urn:akara.test:template-5")
def test_template5():
    from akara.registry import get_service_url
    try:
        params = dict(name="Matt", language="C++", os="Linux", lang="kd")
        yield get_service_url("urn:akara.test:template-1", **params) + "\n"
        yield get_service_url("urn:akara.test:template-2", **params) + "\n"
        yield get_service_url("urn:akara.test:template-3", **params) + "\n"
        yield get_service_url("urn:akara.test:template-4", **params) + "\n"

        params = dict(name=u"\xc5sa", language="C&C#", os= u"G\xf6teborg")
        yield get_service_url("urn:akara.test:template-1", **params) + "\n"
        yield get_service_url("urn:akara.test:template-2", **params) + "\n"
        yield get_service_url("urn:akara.test:template-4", **params) + "\n"

        yield get_service_url("urn:akara.test:template-1", name=u"\xc5sa") + "\n"
        try:
            yield get_service_url("urn:akara.test:template-1", lang=u"\xc5sa") + "\n"
            raise AssertionError
        except KeyError, err:
            assert "name" in str(err)
    except Exception, err:
        yield "Error!"
        yield str(err)
        import traceback, sys
        for line in traceback.format_exception(*sys.exc_info()):
            yield line
        yield "spam"
        
