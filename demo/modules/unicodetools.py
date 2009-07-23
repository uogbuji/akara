# -*- encoding: utf-8 -*-
'''
'''

from __future__ import with_statement

import sys
import urllib, urllib2, urlparse
from cStringIO import StringIO
from gettext import gettext as _
from unicodedata import *

from amara.bindery import html
#from amara.lib.util import *

from akara.services import simple_service, response
from amara.writers.struct import *

NAME_REQUIRED = _("The 'name' query parameter is mandatory.")


def get_first_item(items, errmsg):
    if not items:
        raise AssertionError(errmsg)
    return items[0]

SERVICE_ID = 'http://purl.org/akara/services/builtin/unicode.charbyname'
#@simple_service('get', SERVICE_ID, 'akara.rdfa.json', 'application/json')
@simple_service('GET', SERVICE_ID, 'akara.unicode.charbyname', 'text/plain')
def charbyname(name=None):
    '''
    name - the Unicode character name to look up
    
    Sample request:
    curl "http://localhost:8880/akara.unicode.charbyname?name=DOUBLE+DAGGER"
    '''
    name = get_first_item(name, NAME_REQUIRED)
    try:
        return lookup(name).encode('utf-8')
    except KeyError:
        return ""


Q_REQUIRED = _("The 'q' query parameter is mandatory.")
UINFO_SEARCH_URL = u"http://www.fileformat.info/info/unicode/char/search.htm?preview=entity&"

SERVICE_ID = 'http://purl.org/akara/services/builtin/unicode.search'
@simple_service('GET', SERVICE_ID, 'akara.unicode.search', 'application/xml')
def charsearch(q=None):
    '''
    name - a string to search for in Unicode information (using http://www.fileformat.info )
    
    Sample request:
    curl "http://localhost:8880/akara.unicode.search?q=dagger"
    '''
    q = get_first_item(q, Q_REQUIRED)
    query = urllib.urlencode({"q": q})
    search_url = UINFO_SEARCH_URL + query
    doc = html.parse(search_url)
    buf = StringIO()
    structwriter(indent=u"yes", stream=buf).feed(
    ROOT(
        E((u'characters'),
            (E(u'character', {u'see-also': urlparse.urljoin(search_url, row.td[0].a.href),
                              u'name': unicode(row.td[2]) },
               unicode(row.td[3]))
             for row in doc.xml_select(u'//*[@class="list"]//*[starts-with(@class, "row")]'))
        )
    ))
    return buf.getvalue()

