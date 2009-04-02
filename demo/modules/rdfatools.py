# -*- encoding: utf-8 -*-
'''
'''

import sys, time
import urllib2
#from cgi import parse_qs
#from cStringIO import StringIO
from itertools import *

import simplejson

#from amara.tools.atomtools import feed
from amara.tools import rdfascrape

from akara.services import simple_service, response

#def rdfa2json(url=None):
#Support POST body as well

SERVICE_ID = 'http://purl.org/akara/services/builtin/rdfa.json'
#@simple_service('get', SERVICE_ID, 'akara.rdfa.json', 'application/json')
@simple_service('get', SERVICE_ID, 'akara.rdfa.json', 'application/json')
def rdfa2json(url=None):
    print url
    ids = sets.Set()
    url = url[0]
    if url:
        content = urllib2.urlopen(url).read()
        source = url
    #else:
    #    content = req.body
    #    source = "POST BODY"
    entries = []
    triples = rdfascrape.rdfascrape(content)
    for count, (s, p, o, dt) in enumerate(triples):
        entry = {}
        entry['label'] = '_' + str(count)
        entry['id'] = '_' + str(count)
        pred = p.split('/')[-1].split('#')[-1]
        if pred == u'dc:date' or dt in [u'xsd:date', u'xs:date', u'http://www.w3.org/2001/XMLSchema' + u'date']:
            normalizeddate = feedparser._parse_date(o)
            #date = time.strftime("%Y-%m-%dT%H:%M:%S", feedparser._parse_date(a.group('date').replace('/', ' ') + ' ' + a.group('time')))
            #localizedtime = time.strftime("%a, %d %b %Y %H:%M:%S", feedparser._parse_date(a.group('date').replace('/', ' ') + ' ' + a.group('time')))
            entry[pred] = time.strftime("%Y-%m-%dT%H:%M:%S", normalizeddate)
            entry[pred + u'localized'] = time.strftime("%a, %d %b %Y %H:%M:%S", normalizeddate)
        else:
            entry[pred] = o
        entries.append(entry)
    #print unique_cols
    #print entries
    return simplejson.dumps({'items': entries}, indent=4)

