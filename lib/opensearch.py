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

###############

# I started implementing a parser from the spec then realized the spec
# grammar isn't correctly defined. For example, it has:

#  thost = *( host / tparameter )
#   where
#  host  = IP-literal / IPv4address / reg-name

# which means it allows 127.0.0.1127.0.0.1 as an address.

# I can't simply punt and use Python's urllib.urlsplit because "?"
# is allowed inside of the {} fields,
#  >>> urllib.urlsplit("http://example.com/{spam?}/eggs")
#  SplitResult(scheme='http', netloc='example.com',
#               path='/{spam', query='}/eggs', fragment='')

# I decided to cheat, and rewrite the {}s as {0}, {1}, etc.
# Then split, then search and put those fields back into place.

#### This came from urlparse.urlsplit
# Copied because I have to add "{}" to the following
scheme_chars = urlparse.scheme_chars + "{}"  # tweaked!

# TODO: review and check that I handle the uses_* checks correctly.

def urlsplit(url, scheme='', allow_fragments=True):
    netloc = query = fragment = ''
    i = url.find(':')
    if i > 0:
        if url[:i] == 'http': # optimize the common case
            scheme = url[:i].lower()
            url = url[i+1:]
            if url[:2] == '//':
                netloc, url = urlparse._splitnetloc(url, 2)
            if allow_fragments and '#' in url:
                url, fragment = url.split('#', 1)
            if '?' in url:
                url, query = url.split('?', 1)
            v = urlparse.SplitResult(scheme, netloc, url, query, fragment)
            return v
        for c in url[:i]:
            if c not in scheme_chars:
                break
        else:
            scheme, url = url[:i].lower(), url[i+1:]
    # XXX How to handle this for {} substitutions?
    if (scheme in urlparse.uses_netloc or "{" in scheme) and url[:2] == '//':
        netloc, url = urlparse._splitnetloc(url, 2)
    if allow_fragments and (scheme in urlparse.uses_fragment or "{" in scheme) and '#' in url:
        url, fragment = url.split('#', 1)
    if (scheme in urlparse.uses_query or "{" in scheme) and '?' in url:
        url, query = url.split('?', 1)
    v = urlparse.SplitResult(scheme, netloc, url, query, fragment)
    return v


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


# TODO: how should I check for and handle illegal {fields} ?

tparameter_pat = re.compile(r"""
{{((?P<tprefix> {pchar} ) : )? (?P<tlname> {pchar} ) (?P<tmodifier>\?)? }}
""".format(pchar=pchar), re.X)

assert tparameter_pat.match("{Andrew}")


# Simple intermediate storage
class TemplateVariable(object):
    def __init__(self, tprefix, tlname, is_optional):
        self.tprefix = tprefix
        self.tlname = tlname
        self.is_optional = is_optional

# Convert something like:
#   http://example.com?q={searchTerms}&amp;c={color?}
# into
#   modified_template = http://example.com?q={0}&amp;c={1}
#   variables = [TemplateVariable(None, "searchTerms", 0),
#                TemplateVariable(None, "color", 1)]
#   split_result = SplitResult(scheme = "http", netloc="example.com",
#                              path="", query="q={0}&amp;c={1}")
#


def make_template(template):
    variables = []

    # regex substitution function, used when replacing the tparameter values
    def handle_match(m):
        i = len(variables)
        variables.append( TemplateVariable(m.group("tprefix"),
                                           m.group("tlname"),
                                           m.group("tmodifier") == "?") )
        if variables[-1].tprefix is not None:
            raise AssertionError("namespaces are not supported")
        return "{%d}" % i

    # Replace the terms with {0}, {1}, ...
    modified_template = tparameter_pat.sub(handle_match, template)

    # Based on Python's lenient parser (does not verify, for example,
    # that the scheme contains only valid characters)
    split_result = urlsplit(modified_template)

    return Template(template, variables, split_result)


# Match {0}, {1}, ...
_simple = re.compile(r"{\d+}")

# Used to convert unicode or byte strings into URLs
# Different encoders are needed for different parts

# This is for the scheme
def ascii_encoder(s):
    return s.encode("ascii")

# This is for the host name
def idna_encoder(s):
    return s.encode("idna")

# These are for everything else
def unicode_to_quote_plus(s):
    return urllib.quote_plus(s.encode("utf8"))

def byte_to_quote_plus(s):
    return urllib.quote_plus(s)

_encoders = [(ascii_encoder, ascii_encoder),
             (idna_encoder, idna_encoder),
             (unicode_to_quote_plus, byte_to_quote_plus)]

#print ascii_encoder(u"Espa\u00F1a")

class Template(object):
    def __init__(self, template, variables, split_result):
        self.template = template
        self.variables = variables
        self.split_result = split_result

        # Make lookup a bit easier
        self._lookup = _lookup = {}
        for i, variable in enumerate(variables):
            _lookup["{%d}" % i] = variable
        
    def substitute(self, **kwargs):
        # template substitute function used when replacing the
        # shorten {0}, {1}, ... substrings. Map those back to
        # the TemplateVariable
        def expand(m):
            variable = self._lookup[m.group(0)]
            name = variable.tlname
            if variable.is_optional:
                s = kwargs.get(name, "")
            else:
                s = kwargs[name]
            #print "I have", repr(s)
            # Encode correctly
            if isinstance(s, unicode):
                return unicode_encoder(s)
            return byte_encoder(s)

        #print self.split_result
        unicode_encoder, byte_encoder = _encoders[0]
        scheme = _simple.sub(expand, self.split_result.scheme)

        unicode_encoder, byte_encoder = _encoders[1]
        netloc = _simple.sub(expand, self.split_result.netloc)

        unicode_encoder, byte_encoder = _encoders[2]
        path = _simple.sub(expand, self.split_result.path)
        query = _simple.sub(expand, self.split_result.query)
        fragment = _simple.sub(expand, self.split_result.fragment)

        return urlparse.SplitResult(scheme, netloc, path, query, fragment)

# API still shaky. This is for testing

def apply_template(template, **kwargs):
    t = make_template(template)
    return t.substitute(**kwargs).geturl()
    

import unittest

class Tests(unittest.TestCase):
    def test_no_expansion(self):
        self.assertEquals(apply_template("http://example.com/osd.xml"),
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
        # Although the opensearch spec does not allow this
        # XXX check for the required scheme and host fields?
        apply_template("http://{host?}/")

    def test_unicode_in_scheme(self):
        self.assertRaises(UnicodeEncodeError, apply_template,
                          "{scheme}://blah", scheme=u"Espa\u00F1a")

    def test_unicode_in_host(self):
        # OpenSearch template does not allow this. I do.
        self.assertEquals(apply_template("https://{host}.name/", host=u"Espa\u00F1a"),
                          "https://xn--espaa-rta.name/")

    def test_unicode_in_path(self):
        # I double checked the encoding with Safari. Seems to be right
        self.assertEquals(apply_template("http://google.com/search?q={q}",
                                         q=u"Espa\u00F1a"),
                          "http://google.com/search?q=Espa%C3%B1a")


        
if __name__ == "__main__":
    unittest.main()
