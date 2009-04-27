# -*- encoding: utf-8 -*-
'''
'''

from __future__ import with_statement

import sys, time
import urllib, urllib2
#from cgi import parse_qs
#from cStringIO import StringIO
from gettext import gettext as _
from itertools import *
from functools import *
from unicodedata import *
from contextlib import closing

from amara.bindery import html
from amara.lib.util import *

from akara.services import simple_service, response

NAME_REQUIRED = _("The 'name' query parameter is mandatory.")

SERVICE_ID = 'http://purl.org/akara/services/builtin/unicode.charbyname'
#@simple_service('get', SERVICE_ID, 'akara.rdfa.json', 'application/json')
@simple_service('GET', SERVICE_ID, 'akara.unicode.charbyname', 'text/plain')
def charbyname(name=None):
    '''
    name - the character name to be looked up
    
    Sample request:
    curl "http://localhost:8880/akara.unicode.charbyname?name=DOUBLE+DAGGER"
    '''
    name = first_item(name, next=partial(assert_not_equal, None, msg=NAME_REQUIRED))
    return lookup(name).encode('utf-8')


Q_REQUIRED = _("The 'q' query parameter is mandatory.")
UINFO_SEARCH_PATTERN = u"http://www.fileformat.info/info/unicode/char/search.htm?%s"
UINFO_CHAR_BASE = u"http://www.fileformat.info/info/unicode/char/"

SERVICE_ID = 'http://purl.org/akara/services/builtin/unicode.search'
@simple_service('GET', SERVICE_ID, 'akara.unicode.search', 'application/xml')
def charsearch(q=None):
    '''
    name - a string to search for in Unicode information (using http://www.fileformat.info )
    
    Sample request:
    curl "http://localhost:8880/akara.unicode.search?q=dagger"
    '''
    q = first_item(q, next=partial(assert_not_equal, None, msg=Q_REQUIRED))
    query = urllib.urlencode({'q': q, 'preview': 'entity'})
    doc = html.parse(UINFO_SEARCH_PATTERN%query)
    buf = StringIO()
    structwriter(indent=u"yes", stream=buf).feed(
    ROOT(
        E((u'characters'),
            (E(u'character', {u'see-also': row.td[0].href, u'name': unicode(row.td[2])}, (unicode(row.td[3])))
            for row in doc.xml_select(u'//*[@class="list"]//*[starts-with(@class, "row")]'))
        )
    ))
    return buf.getvalue()

