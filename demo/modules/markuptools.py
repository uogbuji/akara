# -*- encoding: utf-8 -*-
'''
Useful tools for processing markup
'''

from __future__ import with_statement
import sys, time
import urllib, urlparse
from cStringIO import StringIO
from itertools import *

import amara
from amara.bindery import html as htmldoc
from amara.lib.util import trim_word_count

from akara.services import simple_service, response

SERVICE_ID = 'http://purl.org/akara/services/builtin/trim-word-count'
@simple_service('post', SERVICE_ID, 'akara.twc', 'application/xml')
def akara_twc(body, ctype, max=None, html='no'):
    #Note: the masking of the Python built-in max here illustrats the need to
    #Declare overridden param -> kwarg mappings
    '''
    Take some POSTed markup and return a version with words trimmed, but intelligently,
    with understanding of markup, so that tags are not counted, and the structure of
    sub-elements included in the same set is preserved.

    max (query parameter) - which is the maximum word count of the resulting text
    html (query parameter) - if 'yes', try to parse the input as HTML

    Sample request:
    curl --request POST --data-binary "<a>one two <b>three four </b><c>five <d>six seven</d> eight</c> nine</a>" --header "Content-Type: application/xml" "http://localhost:8880/akara.twc?max=7"
    '''
    #Raises ValueError
    #Is there a monadic approach we can provide for Akara for error handling?  This cries out for "Maybe"
    #(OK OK, the idea of Maybe, but more of the simple expressiveness of assert)
    max_ = int(max[0]) if max else 500
    html = html if html is 'no' else html[0]
    if html == 'yes':
        doc = amara.parse(body)
    else:
        doc = htmldoc.parse(body)
    buf = StringIO()
    amara.xml_print(trim_word_count(doc, max_), buf)
    return buf.getvalue()

