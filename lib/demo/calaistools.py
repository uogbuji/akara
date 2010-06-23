# -*- encoding: utf-8 -*-
'''
'''
import sys, time
import urllib2
from gettext import gettext as _

# Requires Python 2.6 or http://code.google.com/p/json/
from amara.thirdparty import json

import amara
from amara.lib.util import *

from akara import module_config
from akara.services import simple_service

#URL_REQUIRED = _("The 'url' query parameter is mandatory.")

APIKEY = module_config[__name__].APIKEY
CALAIS_URL = 'http://service.semanticproxy.com/processurl/%s/rdf/' % APIKEY
    

SERVICE_ID = 'http://purl.org/akara/services/demo/calais.json'
@simple_service('GET', SERVICE_ID, 'akara.calais.json', 'application/json')
def calais2json(url=None):
    '''
    url - the page to run against Calais
    
    Sample request:
    curl "http://localhost:8880/akara.calais.json?url=http://zepheira.com"
    '''
    doc = amara.parse(CALAIS_URL+url[0])
    relations = doc.xml_children[1].xml_value
    entry = {u'id': url}
    for line in relations.splitlines():
        if not line.strip(): continue
        line = line.split(u':')
        key, values = line[0], u':'.join(line[1:]).strip()
        if not values: continue
        vlist = values.split(',')
        entry[key] = values if len(vlist) == 1 else vlist
    return json.dumps({'items': [entry]}, indent=4)

