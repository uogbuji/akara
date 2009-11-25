# Test internal Akara code

from akara.services import convert_body
from amara import tree

# Found a problem in the convert_body code. Returned the XML as a
# string instead of a list containing a single string. Ruined the
# throughput as WSGI processed the result character-by-character.


test_tree = tree.entity()
test_tree.xml_append(tree.element(None, 'spam'))

def test_convert_body_string():
    result = convert_body("Hello", None, None, None)
    assert result == (["Hello"], "text/plain", 5), result

    result = convert_body("Hello", "text/not-plain", None, None)
    assert result == (["Hello"], "text/not-plain", 5), result

def test_convert_body_unicode():
    result = convert_body(u"G\u00f6teborg", None, "utf8", None)
    assert result == (["G\xc3\xb6teborg"], "text/plain; charset=utf8", 9), result

    result = convert_body(u"G\u00f6teborg", "text/not-plain", "utf16", None)
    assert result == (["\xff\xfeG\x00\xf6\x00t\x00e\x00b\x00o\x00r\x00g\x00"], "text/not-plain", 18), result


def test_convert_body_xml():
    result = convert_body(test_tree, None, "utf8", "xml")
    assert result == (['<?xml version="1.0" encoding="utf8"?>\n<spam/>'], "application/xml", 45), result

def test_convert_body_html():
    result = convert_body(test_tree, None, "utf8", "html")
    assert result == (["<spam></spam>"], "text/html", 13), result

def test_convert_body_list():
    result = convert_body(["blah"], None, None, None)
    assert result == (["blah"], "text/plain", None), result

