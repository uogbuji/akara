# -*- encoding: utf-8 -*-
'''
'''
import sys, time
import urllib2
from gettext import gettext as _

# Third-party package from http://code.google.com/p/simplejson/
import simplejson

from amara.lib.util import *
from amara.tools import rdfascrape

from akara.services import simple_service

URL_REQUIRED = _("The 'url' query parameter is mandatory.")

SERVICE_ID = 'http://purl.org/akara/services/builtin/rdfa.json'
@simple_service('GET', SERVICE_ID, 'akara.rdfa.json', 'application/json')
def rdfa2json(url=None):
    '''
    url - the page to check for RDFa
    
    Sample request:
    curl "http://localhost:8880/akara.rdfa.json?url=http://zepheira.com"
    '''
    if url is None:
        raise AssertionError(URL_REQUIRED)
    resources = rdfaparse(url)
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
            # feedparer's internal date parser robustly handles different
            # time formats and returns a 9-tuple
            import feedparser
            normalizeddate = feedparser._parse_date(o)
            obj[pred] = time.strftime("%Y-%m-%dT%H:%M:%S", normalizeddate)
            obj[pred + u'localized'] = time.strftime("%a, %d %b %Y %H:%M:%S", normalizeddate)
        else:
            obj[pred] = o
        resources.append(obj)
    return resources

