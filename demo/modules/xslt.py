# -*- encoding: utf-8 -*-
'''
See also:
'''

from __future__ import with_statement
import sys, time
import urllib, urlparse
from cgi import parse_qs
from cStringIO import StringIO
from itertools import *

import amara
from amara.xslt import transform
from amara.xpath.util import simplify
from amara.bindery import html

from akara.services import simple_service, response

#AKARA_MODULE_CONFIG is automatically defined at global scope for a module running within Akara
DEFAULT_TRANSFORM = AKARA_MODULE_CONFIG.get('default_transform')
#print DEFAULT_TRANSFORM

SERVICE_ID = 'http://purl.org/akara/services/builtin/xslt'
@simple_service('POST', SERVICE_ID, 'akara.xslt')
def akara_xslt(body, ctype, **params):
    '''
    @xslt - URL to the XSLT transform to be applied
    all other query parameters are passed ot the XSLT processor as top-level params
    
    Sample request:
    curl --request POST --data-binary "@foo.xml" --header "Content-Type: application/xml" "http://localhost:8880/akara.xslt?@xslt=http://cvs.4suite.org/viewcvs/*checkout*/4Suite/Ft/Data/identity.xslt"
    '''
    if "@xslt" in params:
        akaraxslttransform = params["@xslt"][0]
    else:
        if not DEFAULT_TRANSFORM:
            raise ValueError('XSLT transform required')
        akaraxslttransform = DEFAULT_TRANSFORM
    import sys; print >> sys.stderr, 'GRIPPO'
    result = transform(body, akaraxslttransform)
    import sys; print >> sys.stderr, 'STACEY'
    import sys; print >> sys.stderr, str(result)
    return response(str(result), result.parameters.media_type)


SERVICE_ID = 'http://purl.org/akara/services/builtin/xpath'
@simple_service('POST', SERVICE_ID, 'akara.xpath', 'text/xml')
def akara_xpath(body, ctype, **params):
    '''
    select - XPath expression to be evaluated against the document
    tidy - 'yes' to tidy HTML, or 'no'

    Sample request:
    curl --request POST --data-binary "@foo.xml" --header "Content-Type: application/xml" "http://localhost:8880/akara.xpath?select=/html/head/title&tidy=yes"
    '''
    if params.get("tidy") == ['yes']:
        doc = html.parse(body)
    else:
        doc = amara.parse(body)
    result = simplify(doc.xml_select(params['select'][0].decode('utf-8')))
    return str(result)

