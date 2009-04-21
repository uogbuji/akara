# -*- encoding: utf-8 -*-
'''
'''

import sys, time
import urllib2
#from cgi import parse_qs
#from cStringIO import StringIO
from gettext import gettext as _
from itertools import *
from unicodedata import *

import simplejson

#from amara.tools.atomtools import feed
from amara.tools import rdfascrape

from akara.services import simple_service, response

NAME_REQUIRED = _("The 'name' query parameter is mandatory.")

SERVICE_ID = 'http://purl.org/akara/services/builtin/unicode.charbyname'
#@simple_service('get', SERVICE_ID, 'akara.rdfa.json', 'application/json')
@simple_service('get', SERVICE_ID, 'akara.unicode.charbyname', 'text/plain')
def charbyname(name=None):
    '''
    name - the character name to be looked up
    
    Sample request:
    curl "http://localhost:8880/akara.rdfa.json?url=http://zepheira.com"
    '''
    name = first_item(name, next=partial(assert_not_equal, None, msg=NAME_REQUIRED))
    return lookup(name).encode('utf-8')

