import server_support
from server_support import server, httplib_server

import urllib, urllib2
from urllib2 import urlopen

import amara

def GET3(name, args=None, data=None):
    url = server() + name
    if args:
        url += "?" + urllib.urlencode(args)
    f = urlopen(url, data)
    s = f.read()
    return f.code, f.headers, s

def GET(name, args=None, data=None):
    code, headers, body = GET3(name, args, data)
    assert code == 200, code
    return body

def test_environment():
    code, headers, body = GET3("test_environment")
    assert code == 200
    assert headers["Content-Type"] == "text/plain"
    assert body == "Good!"

def test_set_path():
    body = GET("test.new.path")
    assert body == "Goody!"

def test_image_gif():
    code, headers, body = GET3("test_image_gif")
    assert headers["Content-Type"] == "image/gif"
    assert body == ('GIF89a\x01\x00\x01\x00\x90\x00\x00\xff\x00\x00\x00'
                    '\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02'
                    '\x02\x04\x01\x00;')

def test_dynamic_content_type():
    code, headers, body = GET3("test_dynamic_content_type")
    assert headers["Content-Type"] == "chemical/x-daylight-smiles"
    assert body == "c1ccccc1O"

def test_unicode_utf8():
    code, headers, body = GET3("test_unicode_utf8")
    assert headers["Content-Type"] == "text/plain; charset=utf-8", headers["Content-Type"]
    assert body == u"\xc5sa bor i G\xf6teborg".encode("utf-8")

def test_unicode_latin1():
    code, headers, body = GET3("test_unicode_latin1")
    assert headers["Content-Type"] == "text/plain", headers["Content-Type"]
    assert body == u"\xc5sa bor i G\xf6teborg".encode("latin1")

def test_unicode_utf16():
    code, headers, body = GET3("test_unicode_utf16")
    assert headers["Content-Type"] == "something/strange", headers["Content-Type"]
    assert body == u"\xc5sa bor i G\xf6teborg".encode("utf16")

def test_xml_utf8():
    code, headers, body = GET3("test_xml_utf8")
    assert headers["Content-Type"] == "application/xml", headers["Content-Type"]
    assert 'encoding="utf-8"?>' in body
    assert u"G\xf6teborg".encode("utf-8") in body, repr(body)
    assert " <something" not in body, body # make sure it is NOT indented

def test_xml_latin1():
    code, headers, body = GET3("test_xml_latin1")
    assert headers["Content-Type"] == "application/xml", headers["Content-Type"]
    assert 'encoding="latin1"?>' in body
    assert u"G\xf6teborg".encode("latin1") in body, repr(body)

def test_xml_utf8_indent():
    code, headers, body = GET3("test_xml_utf8_indent")
    assert headers["Content-Type"] == "application/xml", headers["Content-Type"]
    assert 'encoding="utf-8"?>' in body
    assert u"G\xf6teborg".encode("utf8") in body, repr(body)
    assert " <something" in body, body # make sure it IS indented

def test_list_of_strings():
    code, headers, body = GET3("test_list_of_strings")
    assert headers["Content-Type"] == "text/plain", headers["Content-Type"]
    assert body == "This is a test.\n", body

def test_iterator():
    code, headers, body = GET3("test_iterator")
    assert headers["Content-Type"] == "text/plain", headers["Content-Type"]
    assert body == """\
When shall we three meet again?
In thunder, lightning, or in rain?
When the hurlyburly's done,
When the battle's lost and won.
""", body


def test_args1():
    body = GET("test_args", dict(a="Andrew"))
    assert body == "Hi Andrew and 3"

def test_args2():
    body = GET("test_args", dict(a="Andrew", b="Sara Marie"))
    assert body == "Hi Andrew and Sara Marie"

def test_args2_as_list():
    body = GET("test_args", [("a", "Andrew"), ("b", "Sara Marie")])
    assert body == "Hi Andrew and Sara Marie"

def test_args2_as_list_with_duplicates():
    try:
        body = GET("test_args", [("a", "Andrew"), ("a", "Peter"), ("b", "Sara Marie")])
        raise AssertionError("duplicates should not be allowed!")
    except urllib2.HTTPError, err:
        assert err.code == 400
        s = err.fp.read()
        assert "Using the 'a' query parameter multiple times" in s, s

def test_repeated_args1():
    body = GET("test_repeated_args", dict(a="Andrew"))
    assert body == "Hello ['Andrew'] and 3", repr(body)

def test_repeated_args2():
    body = GET("test_repeated_args", dict(a="Andrew", b="Sara Marie"))
    assert body == "Hello ['Andrew'] and ['Sara Marie']"

def test_repeated_args3():
    body = GET("test_repeated_args", [("a", "Andrew"), ("b", "Sara Marie"), ("a", "Peter")])
    assert body == "Hello ['Andrew', 'Peter'] and ['Sara Marie']"

def test_add_headers():
    code, headers, body = GET3("test_add_headers")
    assert headers["Location"] == "http://freemix.it/"
    # urlopen combines the multiple headers into one.
    # This is completely legit according to the spec.
    assert headers["URL"] == "http://www.xml3k.org/, http://dalkescientific.com/", headers["URL"]


# See if we get back what we went.
def test_echo_simple_get():
    body = GET("test_echo_simple_get", (("a", "1"), ("c", "2"), ("b", "3")))
    assert body == """\
'a' -> '1'
'b' -> '3'
'c' -> '2'
""", body

# Now POST against it, which should fail
def test_echo_simple_get_with_post():
    # this should pass
    GET("test_echo_simple_get", None)
    # this should not pass
    try:
        GET("test_echo_simple_get", None, "Something")
        raise AssertionError("POST to test_echo_simple_get must fail!")
    except urllib2.HTTPError, err:
        assert err.code == 405
        assert "405: Method Not Allowed" in str(err)
        # Required by the HTTP spec
        assert err.headers["Allow"] == "GET, HEAD", err.headers

def test_echo_simple_post():
    body = GET("test_echo_simple_post", data="Heja Sverige!\n")
    assert body == """\
Content-Type: 'application/x-www-form-urlencoded'
Length: 14
Body:
'Heja Sverige!\\n'
""", "Got %r" % (body,)

def test_large_echo():
    body = GET("test_echo_simple_post", data=", ".join(map(str, range(100000))))
    assert "Body:\n'0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, " in body, body[:100]
    assert body.endswith(", 99996, 99997, 99998, 99999'\n"), repr(body[-50:])

def test_echo_simple_post_with_GET():
    try:
        GET("test_echo_simple_post")
        raise AssertionError("GET to test_echo_simple_post must fail!")
    except urllib2.HTTPError, err:
        assert err.code == 405
        assert "405: Method Not Allowed" in str(err)
        # Required by the HTTP spec
        # Also checks that HEAD wasn't added to the header by accident.
        assert err.headers["Allow"] == "POST", err.headers

def test_echo_simple_post_negative_content_length():
    url = server() + "test_echo_simple_post"
    req = urllib2.Request(url, data="I was here.", headers={"Content-Length": "-100"})
    try:
        f = urllib2.urlopen(req)
        raise AssertionError("Not supposed to handle negative lengths")
    except urllib2.HTTPError, err:
        assert err.code == 400

# These have to bypass urllib and work with httplib directly
# in order to generate ill-formatted requests.

def test_good_path():
    h = httplib_server()
    h.request("GET", "/")
    r = h.getresponse()
    assert r.status == 200, r.status

def test_bad_path():
    h = httplib_server()
    # the request is missing the leading '/'
    h.request("GET", "missing_slash")
    r = h.getresponse()
    assert r.status == 400, r.status
    
def test_echo_simple_post_missing_content_length():
    # First, make sure I can call it
    h = httplib_server()
    h.request("POST", "/test_echo_simple_post", "Body",
              {"Content-Length": 4, "Content-Type": "text/plain"})
    r = h.getresponse()
    assert r.status == 200, r.status

    # Try again, this time without a Content-Length
    # (The only way to do that with httplib is to use Content-Length of None)
    h = httplib_server()
    h.request("POST", "/test_echo_simple_post", "Body",
              {"Content-Length": None, "Content-Type": "text/plain"})
    r = h.getresponse()
    # 411 is "Length Required"
    assert r.status == 411, r.status
    

def test_service_no_path():
    code, headers, body = GET3("test_service_no_path")
    assert headers["Content-Type"] == "text/plain"
    assert body == "this uses the default path\n"

def test_service_path():
    code, headers, body = GET3("test_service_path")
    assert headers["Content-Type"] == "text/fancy", headers["Content-Type"]
    assert body == "this specified a path\n"

def test_service_with_a_path():
    # Just checking that it wasn't also registered
    try:
        GET("test_service_with_a_path")
    except urllib2.HTTPError, err:
        assert err.code == 404

## Test that a generator response can still access the query headers
def test_echo_post_headers():
    body = GET("test_echo_post_headers", data="make this a POST")
    assert "HOST ->" in body, body


## Tests for '@method_dispatcher'

def test_dispatching_with_no_methods():
    try:
        GET("test_dispatching_with_no_methods")
        raise AssertionError("test_dispatching_with_no_methods has no methods!")
    except urllib2.HTTPError, err:
        assert err.code == 405, err.code
        assert err.headers.get("Allow", "") == "", repr(err.headers.get("Allow", ""))

def test_dispatching_get_but_with__a_different_name():
    try:
        GET3("test_dispatching_but_with_a_different_name")
        raise AssertionError("test_dispatching_but_with_a_different_name should not work")
    except urllib2.HTTPError, err:
        assert err.code == 404

def test_dispatching_get():
    code, headers, body = GET3("test_dispatching_get")
    assert code == 200
    assert headers["Content-Type"] == "text/plain"
    assert body == "Hi, world!"

def test_dispatching_get_with_arg():
    code, headers, body = GET3("test_dispatching_get", [("a", "Sweden")])
    assert code == 200
    assert headers["Content-Type"] == "text/plain"
    assert body == "Hi, Sweden!", repr(body)
    
def test_dispatching_get_with_wrong_arg():
    try:
        GET("test_dispatching_get", [("b", "Sweden")])
    except urllib2.HTTPError, err:
        # XXX should this be a 400 or 500 error?
        assert err.code == 500, err.code

def test_dispatching_get_with_duplicate_arg():
    try:
        GET("test_dispatching_get", [("a", "Sweden"), ("a", "USA")])
    except urllib2.HTTPError, err:
        assert err.code == 400, err.code
        body = err.read()
        assert "'a' query parameter multiple times" in body, repr(body)

def test_multimethod_get():
    code, headers, body = GET3("test_multimethod", [("a", "Andrew")])
    assert headers["Content-Type"] == "text/fancy"
    assert body == "My name is ['Andrew']. I like 'spam'"
    body = GET("test_multimethod", [("a", "Andrew"), ("b", "lists")])
    assert body == "My name is ['Andrew']. I like ['lists']"
    body = GET("test_multimethod", [("a", "Andrew"),
                                    ("b", "lists"), ("b", "of"), ("b", "things")])
    assert body == "My name is ['Andrew']. I like ['lists', 'of', 'things']"

def test_multimethod_get_bad_args():
    try:
        GET("test_multimethod")
    except urllib2.HTTPError, err:
        assert err.code == 500, err.code
    try:
        GET("test_multimethod", [("qwe", "rty")])
    except urllib2.HTTPError, err:
        assert err.code == 500, err.code


def test_multimethod_post():
    code, headers, body = GET3("test_multimethod", data="some data")
    assert code == 200, code
    assert headers["Content-Type"] == "text/schmancy"
    assert body == """\
You sent 9 bytes of 'application/x-www-form-urlencoded' and 'default value'
First few bytes: 'some data'
""", repr(body)

def test_multimethod_post_with_arg():
    code, headers, body = GET3("test_multimethod", [("a", "something")],
                               data="more data")
    assert code == 200, code
    assert headers["Content-Type"] == "text/schmancy"
    assert body == """\
You sent 9 bytes of 'application/x-www-form-urlencoded' and 'something'
First few bytes: 'more data'
"""

def test_multimethod_post_with_bad_arg():
    try:
        GET3("test_multimethod", [("b", "something")], data="more data")
    except urllib2.HTTPError, err:
        assert err.code == 500
    

def test_multimethod_delete():
    h = httplib_server()
    h.request("DELETE", "/test_multimethod", "[U235]",
              {"Content-Length": 6, "Content-Type": "chemical/x-daylight-smiles"})
    r = h.getresponse()
    assert r.status == 202, r.status

    s = r.read()
    assert s == ('<?xml version="1.0" encoding="utf-8"?>\n'
                 '<nothing city="G\xc3\xb6teborg" name="\xc3\x85sa"><something/></nothing>'), repr(s)


def test_multimethod_teapot():
    h = httplib_server()
    h.request("TEAPOT", "/test_multimethod")
    r = h.getresponse()
    assert r.status == 418, r.status
    s = r.read()
    assert s == "short and stout", repr(s)

# Make a bad request type, see if we get the right responses
def test_multimethod_unknown():
    h = httplib_server()
    # This one isn't supported on the server
    h.request("COFFEEPOT", "/test_multimethod")
    r = h.getresponse()
    assert r.status == 405, r.status
    accept = r.getheader("Allow")
    terms = [s.strip() for s in accept.split(",")]
    terms.sort()
    assert terms == ["DELETE", "GET", "HEAD", "POST", "TEAPOT"], terms

def test_head_vs_get():
    h = httplib_server()
    h.request("GET", "/test_add_headers")
    r = h.getresponse()
    assert r.status == 200, r.status
    get_headers = r.getheaders()
    content_length = r.getheader("content-length")
    assert content_length == "33", content_length
    get_body = r.read()
    assert len(get_body) == 33, (get_body, content_length)

    h.request("HEAD", "/test_add_headers")
    r = h.getresponse()
    assert r.status == 200, r.status
    head_headers = r.getheaders()
    head_body = r.read()
    assert head_body == "", head_body

    assert get_headers == head_headers, (get_headers, head_headers)


# Unicode and XML encoding
def test_method_unicode_latin1():
    code, headers, body = GET3("test_dispatch_unicode")
    assert headers["Content-Type"] == "text/plain; charset=latin1", headers["Content-Type"]
    assert body == u"\xc5sa bor i G\xf6teborg".encode("latin1"), repr(body)

def test_method_unicode_utf8():
    code, headers, body = GET3("test_dispatch_unicode", data="")
    assert headers["Content-Type"] == "text/plain; charset=utf-8", headers["Content-Type"]
    assert body == u"\xc5sa bor i G\xf6teborg".encode("utf8"), repr(body)


expected_utf8 = ('<?xml version="1.0" encoding="utf-8"?>\n'
                 '<nothing city="G\xc3\xb6teborg" name="\xc3\x85sa"><something/></nothing>')
def test_method_xml_utf8():
    code, headers, body = GET3("test_dispatch_xml")
    assert headers["Content-Type"] == "application/xml", headers["Content-Type"]
    assert body == expected_utf8, repr(body)

# Without the byte order marker
expected_utf16 = ('<?xml version="1.0" encoding="utf-16"?>\n'
                  '<nothing city="G\xf6teborg" name="\xc5sa">\n  <something/>\n</nothing>')
def test_method_xml_indent_utf16():
    code, headers, body = GET3("test_dispatch_xml", data="")
    assert headers["Content-Type"] == "application/xml", headers["Content-Type"]

    expected = "\x00".join(expected_utf16) + "\x00"
    assert body == ("\xfe\xff" + expected), repr(body)


# Test the templates
def test_templates():
    url = server()
    f = urlopen(url)
    tree = amara.parse(f)
    nodes = tree.xml_select("//service[@ident='urn:akara.test:template-1']")
    template = (tree.xml_select(
        "//service[@ident='urn:akara.test:template-1']/path/@template")[0].xml_value)
    assert template.endswith("/test.template1?name={name}&language={lang?}"), template

    template = (tree.xml_select(
        "//service[@ident='urn:akara.test:template-2']/path/@template")[0].xml_value)
    assert template.endswith(
        "/test.template2?language={language?}&name={name}&os={os?}"), template

    nodes = (tree.xml_select(
        "//service[@ident='urn:akara.test:template-3']/path/@template"))
    assert len(nodes) == 0, nodes
             
    template = (tree.xml_select(
        "//service[@ident='urn:akara.test:template-4']/path/@template")[0].xml_value)
    assert template.endswith("/test.template4"), template

def test_template_expansion():
    body = GET("test_template5")
    lines = body.splitlines()
    expected = ["server_path: http://dalkescientific.com/",
                "internal_server_path: " + server_support.SERVER_URI]
    for base_uri in (server_support.SERVER_URI,
                     "http://dalkescientific.com/"):
        for suffix in (
            "test.template1?name=Matt&language=kd",
            "test.template2?language=C%2B%2B&name=Matt&os=Linux",
            "test.template4",
            "test.template1?name=%C3%85sa&language=",
            "test.template2?language=C%26C%23&name=%C3%85sa&os=G%C3%B6teborg",
            "test.template4",
            "test.template1?name=%C3%85sa&language=",
            ):
            expected.append( base_uri + suffix )

    assert len(lines) == len(expected), (len(lines), len(expected))

    for expected_line, got_line in zip(expected, lines):
        print repr(expected_line), repr(got_line)
        assert expected_line == got_line, (expected_line, got_line)
    # This is to check line length mismatch
    assert expected == lines, (expected, lines)

## Test the additionally registered external services
def test_additional_services():
    body = GET("test_extra_call", dict(service_id="urn:service_reg:1", x="Andrew"))
    expected = ("URL: %stest.template1?name=Andrew&language=FORTRAN\n"
                "Andrew uses FORTRAN on unix") % (server_support.SERVER_URI,)
    assert body == expected, (body, expected)

    # As a side-effect, the previous called akara_tests.py:_delayed_install()
    body = GET("test_extra_call", dict(service_id="urn:akara.test:extra_echo",
                                       bar="baz"))
    expected = ("URL: %stest_echo_simple_get?foo=baz\n"
                "'foo' -> 'baz'\n") % (server_support.SERVER_URI,)
    assert body == expected, (body, expected)
