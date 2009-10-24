from server_support import server

import urllib, urllib2
from urllib2 import urlopen

def GET3(name, args=None):
    url = server() + name
    if args:
        url += "?" + urllib.urlencode(args)
    f = urlopen(url)
    s = f.read()
    return f.code, f.headers, s

def GET(name, args=None):
    code, headers, body = GET3(name, args)
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

def test_repeated_args1():
    body = GET("test_repeated_args", dict(a="Andrew"))
    assert body == "Hello ['Andrew'] and 3", repr(body)

def test_repeated_args2():
    body = GET("test_repeated_args", dict(a="Andrew", b="Sara Marie"))
    assert body == "Hello ['Andrew'] and ['Sara Marie']"

def test_repeated_args3():
    body = GET("test_repeated_args", [("a", "Andrew"), ("b", "Sara Marie"), ("a", "Peter")])
    assert body == "Hello ['Andrew', 'Peter'] and ['Sara Marie']"
