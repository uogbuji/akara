# -*- coding: iso-8859-1 -*-
# 
"""
"""
#Detailed license and copyright information: http://4suite.org/COPYRIGHT

__all__ = [
    "WIKITEXT_IMT", "DOCBOOK_IMT", "RDF_IMT", "HTML_IMT", "ATTACHMENTS_IMT",
    "ORIG_BASE_HEADER", "ATTACHMENTS_MODEL_XML", "ATTACHMENTS_MODEL",
    "MOIN_DOCBOOK_MODEL_XML", "MOIN_DOCBOOK_MODEL",
]

import sys
import os
import cgi
#import pprint
import httplib, urllib, urllib2, cookielib
#from wsgiref.util import shift_path_info, request_uri
from string import Template
from cStringIO import StringIO
import tempfile
from gettext import gettext as _
from functools import *
from itertools import *
from operator import *

import amara
from amara import bindery
from amara.writers.struct import *
from amara.bindery.model import *

WIKITEXT_IMT = 'text/plain'
HTML_IMT = 'text/html'
DOCBOOK_IMT = 'application/docbook+xml'
RDF_IMT = 'application/rdf+xml'
ATTACHMENTS_IMT = 'application/x-moin-attachments+xml'
ORIG_BASE_HEADER = 'x-akara-wrapped-moin'

# XML models

ATTACHMENTS_MODEL_XML = '''<?xml version="1.0" encoding="UTF-8"?>
<attachments xmlns:eg="http://examplotron.org/0/" xmlns:ak="http://purl.org/xml3k/akara/xmlmodel">
  <attachment href="" ak:rel="name()" ak:value="@href"/>
</attachments>
'''

ATTACHMENTS_MODEL = examplotron_model(ATTACHMENTS_MODEL_XML)

MOIN_DOCBOOK_MODEL_XML = '''<?xml version="1.0" encoding="UTF-8"?>
<article xmlns:eg="http://examplotron.org/0/" xmlns:ak="http://purl.org/xml3k/akara/xmlmodel" ak:resource="">
  <ak:rel name="'ak-old-type'" ak:value="glosslist[1]/glossentry[glossterm='akara:type']/glossdef//ulink/@url"/>
  <ak:rel name="'ak-type'" ak:value="section[title='akara:metadata']/glosslist/glossentry[glossterm='akara:type']/glossdef//ulink/@url"/>
  <ak:rel name="'ak-updated'" ak:value="articleinfo/revhistory/revision[1]/date"/>
  <articleinfo>
    <title ak:rel="name()" ak:value=".">FrontPage</title>
    <revhistory>
      <revision eg:occurs="*">
        <revnumber>15</revnumber>
        <date>2009-02-22 07:45:22</date>
        <authorinitials>localhost</authorinitials>
      </revision>
    </revhistory>
  </articleinfo>
  <section eg:occurs="*" ak:resource="">
    <title ak:rel="name()" ak:value=".">A page</title>
    <para>
    Using: <ulink url="http://moinmo.in/DesktopEdition"/> set <code>interface = ''</code>)
    </para>
    <itemizedlist>
      <listitem>
        <para>
          <ulink url="http://localhost:8080/Developer#">Developer</ulink> </para>
      </listitem>
    </itemizedlist>
  </section>
</article>
'''

MOIN_DOCBOOK_MODEL = examplotron_model(MOIN_DOCBOOK_MODEL_XML)

