# -*- encoding: utf-8 -*-
'''
'''
from __future__ import with_statement

import sys, time
import urllib2
#from cgi import parse_qs
#from cStringIO import StringIO
from gettext import gettext as _
from itertools import *
from functools import *
from contextlib import closing

import simplejson

from amara.lib.util import *
from amara.tools import rdfascrape

from akara.services import simple_service, response

#def rdfa2json(url=None):
#Support POST body as well

URL_REQUIRED = _("The 'url' query parameter is mandatory.")

SERVICE_ID = 'http://purl.org/akara/services/builtin/rdfa.json'
#@simple_service('get', SERVICE_ID, 'akara.rdfa.json', 'application/json')
@simple_service('GET', SERVICE_ID, 'akara.rdfa.json', 'application/json')
def rdfa2json(url=None):
    '''
    url - the page to check for RDFa
    
    Sample request:
    curl "http://localhost:8880/akara.rdfa.json?url=http://zepheira.com"
    '''
    ids = set()
    url = first_item(url, next=partial(assert_not_equal, None, msg=URL_REQUIRED))
    with closing(urllib2.urlopen(url)) as resp:
        content = resp.read()
    resources = rdfaparse(content)
    return simplejson.dumps({'items': resources}, indent=4)
    

def rdfaparse(content):
    resources = []
    triples = rdfascrape.rdfascrape(content)
    for count, (s, p, o, dt) in enumerate(triples):
        obj = {}
        obj['label'] = '_' + str(count)
        obj['id'] = '_' + str(count)
        pred = p.split('/')[-1].split('#')[-1]
        if pred == u'dc:date' or dt in [u'xsd:date', u'xs:date', u'http://www.w3.org/2001/XMLSchema' + u'date']:
            normalizeddate = feedparser._parse_date(o)
            #date = time.strftime("%Y-%m-%dT%H:%M:%S", feedparser._parse_date(a.group('date').replace('/', ' ') + ' ' + a.group('time')))
            #localizedtime = time.strftime("%a, %d %b %Y %H:%M:%S", feedparser._parse_date(a.group('date').replace('/', ' ') + ' ' + a.group('time')))
            obj[pred] = time.strftime("%Y-%m-%dT%H:%M:%S", normalizeddate)
            obj[pred + u'localized'] = time.strftime("%a, %d %b %Y %H:%M:%S", normalizeddate)
        else:
            obj[pred] = o
        resources.append(obj)
    #print unique_cols
    #print entries
    return resources

