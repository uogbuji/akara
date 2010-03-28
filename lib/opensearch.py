"""Support library for OpenSearch templates

This is an internal module to Akara. The API may change in the future.

"""

import re
import urlparse
import urllib


### Some examples from various sources (mostly the spec document)
# http://example.com/search?q={searchTerms}
# http://example.com/feed/{startPage?}
# http://example.com?q={searchTerms}&amp;c={example:color?}
# http://example.com?q={a:localname?}
# http://example.com?f={example:format?}
# http://example.com/search?color={custom:color?}
# http://example.com/?q={searchTerms}&amp;pw={startPage?}
# http://example.com/?q={searchTerms}&amp;pw={startPage?}&amp;format=rss
# http://example.com/?q={searchTerms}&amp;pw={startPage?}&amp;format=atom
# http://example.com/osd.xml

# http://example.com/ab{name?}/with?arg={arg}
# http://{country}.example.com/

### Syntax definitions from the relevant specs

# tparameter     = "{" tqname [ tmodifier ] "}"
# tqname = [ tprefix ":" ] tlname
# tprefix = *pchar
# tlname = *pchar

# pchar = unreserved / pct-encoded / sub-delims / ":" / "@"

# unreserved    = ALPHA / DIGIT / "-" / "." / "_" / "~"
# pct-encoded   = "%" HEXDIG HEXDIG
# sub-delims    = "!" / "$" / "&" / "'" / "(" / ")"
#                 / "*" / "+" / "," / ";" / "="

# tmodifier      = "?"

pchar = r"""([A-Za-z0-9._~!$&''()*+,;=""-]|(%[0-9A-Fa-f]{2}))*"""
scheme = r"[a-zA-Z0-9+.-]+"
tparameter = r"""
(?: {{
       ((?P<tprefix> {pchar} ) : )?
       (?P<tlname> {pchar} )
       (?P<tmodifier>\?)?
    }} )
""".format(pchar=pchar)


scheme_pat = re.compile(r"""( {scheme} | {tparameter}):""".format(
    scheme=scheme, tparameter=tparameter), re.X)

tparameter_pat = re.compile(r"""
{{((?P<tprefix> {pchar} ) : )? (?P<tlname> {pchar} ) (?P<tmodifier>\?)? }}
""".format(pchar=pchar), re.X)

# Match either a tparameter or things which aren't in a template
template_pat = re.compile(r"({tparameter}|[^{{]+)".format(tparameter=tparameter), re.X)


###############

# I started by looking for existing OpenSearch implementations but
# they didn't work correctly. For example, one tool uses
# urllib.urlsplit to parse the fields, then does template substitution
# of each field. That works only because the library didn't support
# optional "?" fields. That is, consider:

#  >>> urllib.urlsplit("http://example.com/{spam?}/eggs")
#  SplitResult(scheme='http', netloc='example.com',
#               path='/{spam', query='}/eggs', fragment='')

# I started implementing a parser from the spec then realized the spec
# grammar isn't correctly defined. For example, it has:

#  thost = *( host / tparameter )
#   where
#  host  = IP-literal / IPv4address / reg-name

# which means it allows 127.0.0.1127.0.0.1 as an address. While the
# grammar isn't that bad, it's easier to use an approach more like
# what Python's urllib.urlsplit does.

# I also noticed the grammar doesn't allow http://{userid}.myopenid.com/
# as a template, which seemed important for some cases.

# I can't treat this as a simple template grammar and just search for
# the {...} tokens because of Unicode issues. The encoding is field
# specific. The hostname uses IDNA while most of the rest of the
# encoding uses URL-encoded UTF-8.

# The algorithm breaks the template up into parts. Each part is either
# a string (should be a byte string since URLs are not Unicode) or a
# function corresponding to a template lookup. The function will get a
# dictionary of input parameters and it must returns the correctly
# encoded value.

# Template substitution is a merger of either the byte string or the
# result of calling the function with the input parameters.


def is_optional(m):
    return m.group("tmodifier") == "?"

def _parse_scheme(uri):
    # Something like "http:", "ftp:", or "{scheme}:"
    m = scheme_pat.match(uri)
    if m is None:
        i = uri.find(":")
        if i >= 0:
            msg = "URI scheme must be either text or a single template field: %r"
        else:
            msg = "Missing or unparsable URI scheme: %r"
            
        raise TypeError(msg % (uri,))

    if m.group("tlname") is None:
        # Just text
        return m.end(), [m.group(0).encode("ascii")]

    if is_optional(m):
        raise TypeError("URI scheme cannot be an optional template variable")
    def convert_scheme(params, tlname=m.group("tlname")):
        # I could make this a more rigorous test for the legal scheme characters
        return params[tlname].encode("ascii")  # the scheme can only be ASCII

    return m.end(), [convert_scheme, ":"]

# Find the end of the network location field. The start is just after the '//'.
# To make things easier, this must be a string with all {names} removed!
# That's the "xuri", which uses "X"s to replace the template names.
def _find_netloc(xuri, start):
    end = len(xuri)
    for c in "/?#":
        offset = xuri.find(c, start)
        if offset >= 0 and offset < end:
            end = offset
    return end

def _parse_netloc(netloc, xnetloc):
    i = xnetloc.find("@")
    if i >= 0:
        # Use the normal utf-8 encoding
        for part in _parse_template(netloc[:i]):
            yield part
        yield "@"
        hostname = netloc[i+1:]
        xhostname = xnetloc[i+1:]
    else:
        hostname = netloc
        xhostname = xnetloc

    i = xhostname.find(":")
    if i >= 0:
        port = hostname[i+1:]
        hostname = hostname[:i]
    else:
        port = None

    if not hostname:
        raise TypeError("Akara requires a hostname in the template")

    # This is tricky. I have to join all of the subfields before doing
    # the idna encoding. This allows u"{hostname}.Espa\u00F1a.com"
    # since the u".Espa\u00F1a.com" does not encode on its own.

    # Create a list of subparts, either:
    #    - strings which are *not* encoded
    #    - a function to look up the value in the dictionary
    subparts = []
    for m in template_pat.finditer(hostname):
        tlname = m.group("tlname")
        if tlname is None:
            subparts.append(m.group(0))
        else:
            if m.group("tmodifier") == "?":
                raise TypeError("URI hostname cannot contain an optional template variable")
            subparts.append(lambda d, tlname=tlname: d[tlname])

    # In the common case this is a string. No need for the extra overhead.
    if len(subparts) == 1 and isinstance(subparts[0], basestring):
        yield subparts[0].encode("idna")

    else:
        # Function to convert, join, and encode based the parts
        def convert_hostname(params, parts=subparts):
            results = []
            for part in parts:
                if isinstance(part, basestring):
                    results.append(part)
                else:
                    results.append(part(params))
            result = "".join(results)
            return result.encode("idna")
        yield convert_hostname

    # And finally, the port.
    if port is None:
        return

    # If it's just a number, return the number (and the ":" I had removed)
    if port.isdigit():
        yield ":" + port

    # Otherwise it's a parameter. Make sure it's only a paramter
    m = tparameter_pat.match(port)
    if m is None:
        raise TypeError("Port must be either a number or a template name")
    if m.end() != len(port):
        raise TypeError("Port may not contain anything after the template name")
    tlname = m.group("tlname")
    if is_optional(m):
        extract = lambda params, tlname=tlname: params.get(tlname, "")
    else:
        extract = lambda params, tlname=tlname: params[tlname]
    def convert_port(params, extract=extract, tlname=tlname):
        value = extract(params)
        if isinstance(value, int):
            # Allow people to pass in a port number as an integer
            return ":%d" % (value,)
        if value == "":
            # No port given? Use the default. (Don't include the ':' here.)
            return ""
        if value.isdigit():
            return ":" + value
        raise TypeError("Port template parameter %r is not an integer (%r)" %
                        (tlname, value))
    yield convert_port
            

def _parse_template(template):
    for m in template_pat.finditer(template):
        if m.group("tlname") is None:
            # "ascii" to ensure that no Unicode characters are in the template
            yield m.group(0).encode("ascii")
        else:
            if is_optional(m):
                def convert_scheme(params, tlname=m.group("tlname")):
                    return urllib.quote_plus(params.get(tlname, "").encode("utf8"))
            else:
                def convert_scheme(params, tlname=m.group("tlname")):
                    return urllib.quote_plus(params[tlname].encode("utf8"))
            yield convert_scheme


def decompose_template(uri):
    # For use in Akara, the scheme and host name are required, and the
    # "uri" syntax is defined from RFC 3986 + OpenSearch templates.

    # I'll make life easier by working with a string without the {} templates.
    def check_and_replace_template_field(m):
        if m.group("tprefix") is not None:
            raise TypeError("Template prefix not supported in Akara (in %r)" % (m.group(0),))
        
        if m.group("tlname") == "":
            raise TypeError("Empty template variable in %r" % (uri,))
        return "X" * (m.end() - m.start())
            
    xuri = tparameter_pat.sub(check_and_replace_template_field, uri)

    # Make sure that no "{" or "}" characters are present!
    if "{" in xuri:
        raise TypeError(
            "Unexpected '{' found in URI at position %d)" % (xuri.index("{")+1,))
    if "}" in xuri:
        raise TypeError(
            "Unexpected '}' found in URI at position %d" % (xuri.index("}")+1,))

    parts = []

    # "http:", "ftp:", "{scheme}:"
    start, subparts = _parse_scheme(uri)
    parts.extend(subparts)

    # Check for the "//" in things like "http://example.com"
    if uri[start:start+2] != "//":
        raise TypeError("Missing required '//' in URI (scheme and hostname must be given)")
    assert isinstance(parts[-1], basestring)
    # This is either something like ["http:"] or something like [<function>. ":"]
    # Optimize by merging the last item with the "//"
    parts[-1] += "//"
    start += 2

    # [tuserinfo "@"] thost [ ":" tport ]
    # The OpenSearch template makes this harder to find. I have to consider:
    #    http://example.com?spam
    #    http://{host?}?spam
    #    http://example.com/spam
    #    http://example.com#spam
    #    ftp://userid:password@ftp
    #    ftp://{userid?}:{password?}@{userid}.example.com/

    # Since I've replaced the templates with "X"s, this becomes a lot easier.
    end = _find_netloc(xuri, start)
    netloc  =  uri[start:end]
    xnetloc = xuri[start:end]

    # The userid portion is encoded different than the hostname
    parts.extend(_parse_netloc(netloc, xnetloc))

    # And the rest is a simple encoding
    parts.extend(_parse_template(uri[end:]))

    return parts


class Template(object):
    def __init__(self, template, terms):
        self.template = template
        self.terms = terms
    def substitute(self, **kwargs):
        results = []
        for term in self.terms:
            if isinstance(term, basestring):
                results.append(term)
            else:
                results.append(term(kwargs))
        return "".join(results)

def make_template(template):
    terms = decompose_template(template)
    return Template(template, terms)

# API still shaky. This is for testing

def apply_template(template, **kwargs):
    t = make_template(template)
    return t.substitute(**kwargs)


import unittest

class Tests(unittest.TestCase):
    def raisesTypeError(self, f, *args, **kwargs):
        try:
            raise AssertionError( f(*args, **kwargs) )
        except TypeError, err:
            return str(err)

    #### These test the public API
    def test_no_expansion(self):
        self.assertEquals(apply_template("http://example.com/osd.xml"),
                          "http://example.com/osd.xml")
        self.assertEquals(apply_template(u"http://example.com/osd.xml"),
                          "http://example.com/osd.xml")
        
    def test_single_term(self):
        self.assertEquals(apply_template("http://example.com/search?q={searchTerms}",
                                         searchTerms="Andrew"),
                          "http://example.com/search?q=Andrew")
    def test_spaces(self):
        self.assertEquals(apply_template("http://example.com/search?q={searchTerms}",
                                         searchTerms="Andrew Dalke"),
                          "http://example.com/search?q=Andrew+Dalke")

    def test_many(self):
        T = "{scheme}://{host}:{port}/{path}?q={arg}#{hash}"
        self.assertEquals(apply_template(T, scheme="gopher",
                                         host="hole", port="70",
                                         path="somewhere/else",
                                         arg="spam & eggs",
                                         hash="browns"),
                          "gopher://hole:70/somewhere%2Felse?q=spam+%26+eggs#browns")
    def test_failure(self):
        self.assertRaises(KeyError, apply_template, "http://{host}/")

    def test_optional(self):
        self.assertEquals(apply_template("http://example.com/{arg?}"),
                          "http://example.com/")
        self.assertEquals(apply_template("http://example.com/{arg?}{arg?}"),
                          "http://example.com/")
        self.assertEquals(apply_template("http://example.com/{arg?}{arg?}", arg="X"),
                          "http://example.com/XX")

    def test_optional_in_scheme(self):
        err = self.raisesTypeError(apply_template, "{scheme?}://example.com/",
                                   scheme="gopher")
        assert err.startswith("URI scheme cannot be an optional template variable")

    def test_optional_in_hostname(self):
        err = self.raisesTypeError(apply_template, "scheme://{hostname?}.com/",
                                   hostname="example")
        assert err.startswith("URI hostname cannot contain an optional template variable")

    def test_port(self):
        self.assertEquals(apply_template("http://example.com:{port}/", port="80"),
                          "http://example.com:80/")
        self.assertEquals(apply_template("http://example.com:{port?}/", port="80"),
                          "http://example.com:80/")


    def test_unicode_failures(self):
        # Scheme cannot include Unicode
        self.assertRaises(UnicodeEncodeError, apply_template,
                          "{scheme}://blah", scheme=u"Espa\u00F1a")
        # Don't allow non-ascii characters except in the domain
        self.assertRaises(UnicodeEncodeError, apply_template,
                          u"http://google.com/search?q=Espa\u00F1a")
        self.assertRaises(UnicodeEncodeError, apply_template,
                          u"http://\u00F1{q}@example.com")
        

    def test_multiple_args_in_scheme(self):
        for (target, expected_err) in (
            ("{scheme}{scheme}://example.com/", "text or a single template field"),
            ("blah{scheme}://example.com", "text or a single template field"),
            ("blah/", "Missing or unparsable"),
            ):
            err = self.raisesTypeError(apply_template, target, scheme="http")
            assert expected_err in err, (target, expected_err, err)

    def test_unicode_in_host(self):
        # OpenSearch template does not allow this. I do.
        self.assertEquals(apply_template("https://{host}.name/", host=u"Espa\u00F1a"),
                          "https://xn--espaa-rta.name/")
        # I also allow Unicode in the host name (but only there!)
        self.assertEquals(apply_template(u"https://{host}.name/", host=u"Espa\u00F1a"),
                          "https://xn--espaa-rta.name/")
        self.assertEquals(apply_template(u"https://{host}.a\u00F1o/",
                                         host=u"Espa\u00F1a"),
                          "https://xn--espaa-rta.xn--ao-zja/")

    def test_unicode_in_host_part(self):
        # I double checked the encoding with Safari. Seems to be right
        self.assertEquals(apply_template(u"https://{host}.Espa\u00F1a/", host=u"a\u00F1o"),
                          "https://xn--ao-zja.xn--espaa-rta/")
        self.assertEquals(apply_template(u"http://{host}.\u00F1.name/", host=u"Espa\u00F1a"),
                          "http://xn--espaa-rta.xn--ida.name/")

    def test_unicode_in_path(self):
        # I double checked the encoding with Safari. Seems to be right
        self.assertEquals(apply_template("http://google.com/search?q={q}",
                                         q=u"Espa\u00F1a"),
                          "http://google.com/search?q=Espa%C3%B1a")
        self.assertEquals(apply_template(u"http://google.com/search?q={q}",
                                         q=u"Espa\u00F1a"),
                          "http://google.com/search?q=Espa%C3%B1a")


    def test_unicode_in_username(self):
        self.assertEquals(apply_template("http://{q}@example.com",
                                         q=u"Espa\u00F1a"),
                          "http://Espa%C3%B1a@example.com")


    def test_using_prefix(self):
        for uri in ("{spam:x}://dalke:blah@example.com/something",
                    "HTTP://{spam:x}:blah@example.com/something",
                    "HTTP://{spam:x}:blah@example.com/something",
                    "HTTP://dalke:{spam:x}@example.com/something",
                    "HTTP://dalke:blah@{spam:x}.com/something",
                    "HTTP://dalke:blah@example.com/{spam:x}"):
            err = self.raisesTypeError(apply_template, uri)
            assert err.startswith("Template prefix not supported in Akara (in '"), err
            # While this should work just fine
            t = apply_template(uri.replace("spam:", ""), x="123")

    def test_missing_slashes(self):
        for uri in ("http:spam",
                    "http:/spam",
                    "http:/?spam"):
            err = self.raisesTypeError(apply_template, uri)
            assert err.startswith("Missing required '//' in URI"), err
    def test_missing_hostname(self):
        for uri in ("http:///spam/",
                    "http:///spam",
                    "http://dalke@/spam",
                    "http://:@/spam",
                    "http://?spam"):
            err = self.raisesTypeError(apply_template, uri)
            assert err.startswith("Akara requires a hostname in the template"), err

    def test_empty_template_name(self):
        for uri in ("{}://example.com/",
                    "http://{}/",
                    "http://example.com?{}"):
            err = self.raisesTypeError(apply_template, uri)
            assert err.startswith("Empty template variable in '")
                    
    def test_bad_templates(self):
        for uri, c in (("{scheme://example.com/whatever}", "{"),
                       ("{scheme}://example.com/whatever}", "}"),
                       ("http://example.com?whatever=asdf#}", "}"),
                       ("http://example.com?whatever=asdf#{", "{")):
            err = self.raisesTypeError(apply_template, uri)
            assert err.startswith("Unexpected '" + c + "' found in URI"), err

    def test_port_errors(self):
        err = self.raisesTypeError(apply_template, "http://localhost:/")
        assert err.startswith("Port must be either a number or a template name")
        err = self.raisesTypeError(apply_template, "http://localhost:/a")
        assert err.startswith("Port must be either a number or a template name")
        err = self.raisesTypeError(apply_template, "http://localhost:{port}a/")
        assert err.startswith("Port may not contain anything after the template name"), err
        err = self.raisesTypeError(apply_template, "http://localhost:{port}/", port="q")
        assert err.startswith("Port template parameter 'port' is not an integer ('q')"), err
        err = self.raisesTypeError(apply_template, "http://localhost:{port}/", port="-80")
        assert err.startswith("Port template parameter 'port' is not an integer ('-80')")

    def test_port(self):
        self.assertEquals(apply_template("http://localhost:{port}/", port=8080),
                          "http://localhost:8080/")
        self.assertEquals(apply_template("http://localhost:{port}/", port="8080"),
                          "http://localhost:8080/")
        self.assertEquals(apply_template("http://localhost:{port}/abc", port=""),
                          "http://localhost/abc")
        self.assertEquals(apply_template("http://localhost:{port?}/?q"),
                          "http://localhost/?q")
        self.assertEquals(apply_template("http://localhost:{port?}/?q", port="123"),
                          "http://localhost:123/?q")
        
if __name__ == "__main__":
    unittest.main()
