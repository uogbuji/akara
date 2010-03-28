"""Support library for OpenSearch templates

This is an internal module to Akara. The API may change in the future.

"""

import re
import urlparse
import urllib


__all__ = ["make_template", "apply_template"]

# The OpenSearch format is documented at
#   http://www.opensearch.org/Specifications/OpenSearch/1.1/Draft_4
# it references the URI spec at
#   http://www.ietf.org/rfc/rfc3986.txt
# Note a proposed extension to OpenSearch at:
#   http://www.snellspace.com/wp/?p=369


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

# Test if the re match group contains the '?' tmodifier field
def _is_optional(m):
    return m.group("tmodifier") == "?"

##################


# Parse the URI scheme field.
# Looks something like "http:", "ftp:", or "{scheme}:"
# This parses up to the ':' and returns the offset to the ':' and a
# list of template parts.
def _parse_scheme(uri):
    m = scheme_pat.match(uri)
    if m is None:
        i = uri.find(":")
        if i >= 0:
            msg = "URI scheme must be either text or a single template field: %r"
        else:
            msg = "Missing or unparsable URI scheme: %r"
            
        raise TypeError(msg % (uri,))

    if m.group("tlname") is None:
        # Just text. This must be an ASCII byte string.
        return m.end(), [m.group(0).encode("ascii")]

    if _is_optional(m):
        raise TypeError("URI scheme cannot be an optional template variable")
    def convert_scheme(params, tlname=m.group("tlname")):
        # I could make this a more rigorous test for the legal scheme characters
        return params[tlname].encode("ascii")  # the scheme can only be ASCII

    return m.end(), [convert_scheme, ":"]

# Find the end of the network location field. The start is just after the '//'.
# To make things easier, this must be a string with all template {names} removed!
# That's the "xuri", which uses "X"s to replace the template names.
def _find_netloc(xuri, start):
    end = len(xuri)
    # This is the same test in urllib.urlsplit
    for c in "/?#":
        offset = xuri.find(c, start)
        if offset >= 0 and offset < end:
            end = offset
    return end

def _parse_netloc(netloc, xnetloc):
    # Check to see if there's a username/password field.
    # These happen before the '@', if one exists.
    i = xnetloc.find("@")
    if i >= 0:
        # Username/password fields use the normal utf-8 encoding
        # so handle that with the normal template parser.
        for part in _parse_template(netloc[:i]):
            yield part
        yield "@"
        hostname = netloc[i+1:]
        xhostname = xnetloc[i+1:]
    else:
        hostname = netloc
        xhostname = xnetloc

    # There could be a port after the hostname. 
    # Starts with ":", as in  http://localhost:8080/path/
    i = xhostname.find(":")
    if i >= 0:
        port = hostname[i+1:]
        hostname = hostname[:i]
    else:
        # No port specified
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
        return

    # Otherwise it's a parameter. Make sure it's only a paramter
    m = tparameter_pat.match(port)
    if m is None:
        raise TypeError("Port must be either a number or a template name")
    if m.end() != len(port):
        raise TypeError("Port may not contain anything after the template name")
    tlname = m.group("tlname")
    if _is_optional(m):
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
            
# Handle the text fields which are escaped via URL-encoded UTF-8
def _parse_template(template):
    for m in template_pat.finditer(template):
        if m.group("tlname") is None:
            # "ascii" to ensure that no Unicode characters are in the template
            yield m.group(0).encode("ascii") # You must pre-encode non-ASCII text yourself
        else:
            if _is_optional(m):
                def convert_scheme(params, tlname=m.group("tlname")):
                    return urllib.quote_plus(params.get(tlname, "").encode("utf8"))
            else:
                def convert_scheme(params, tlname=m.group("tlname")):
                    return urllib.quote_plus(params[tlname].encode("utf8"))
            yield convert_scheme


def decompose_template(uri):
    """Internal function to break down an OpenSearch template into its Template terms"""
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
    """A parsed OpenSearch Template object.

    Use 'make_template(template_string)' to make a Template instance.
    """
    def __init__(self, template, terms):
        """You should not call this constructor directly."""
        self.template = template
        self.terms = terms
    def substitute(self, **kwargs):
        """Use the kwargs to fill in the template fields.

        Unknown kwargs are ignored.
        """
        results = []
        for term in self.terms:
            if isinstance(term, basestring):
                results.append(term)
            else:
                results.append(term(kwargs))
        return "".join(results)

def make_template(template):
    """Given an OpenSearch template, return a Template instance for it.

    >>> template = make_template('http://localhost/search?q={term}')
    >>> template.substitute(term='opensearch syntax')
    'http://localhost/search?q=opensearch+syntax'
    >>>
    """
    terms = decompose_template(template)
    return Template(template, terms)

def apply_template(template, **kwargs):
    """Apply the kwargs to the template fields and return the result

    >>> apply_template('http://{userid}.example.com/status', userid='anonymous')
    'http://anonymous.example.com/status'
    >>>
    """
    t = make_template(template)
    return t.substitute(**kwargs)

