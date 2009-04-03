# -*- encoding: utf-8 -*-
'''
Requires http://pypi.python.org/pypi/icalendar/
easy_install icalendar
'''

import urllib, urllib2
from itertools import *

import simplejson
from icalendar import Calendar, Event

#from amara.tools.atomtools import feed
from akara.services import simple_service, response

SERVICE_ID = 'http://purl.org/akara/services/builtin/ical.json'
@simple_service('post', SERVICE_ID, 'ical.json', 'application/json')
def ical2json(body, ctype):
    '''
    Convert iCalendar info to Exhibit JSON
    (see: http://www.ibm.com/developerworks/web/library/wa-realweb6/ )

    Sample request:
    * curl --request POST --data-binary "@foo.ics" --header "Content-Type: text/calendar" "http://localhost:8880/ical.json"
    '''
    ids = set()
    entries = []
    cal = Calendar.from_string(body)
    #[ c['UID'] for c in  cal.subcomponents if c.name == 'VEVENT' ]
    for count, component in enumerate(cal.walk()):
        #if count > MAXRECORDS: break
        if component.name != 'VEVENT': continue
        entry = {}
        entry['summary'] = unicode(component['SUMMARY'])
        entry['label'] = entry['summary'] + '_' + str(count)
        entry['description'] = unicode(component['DESCRIPTION'])
        entry['start'] = component['DTSTART'].dt.isoformat()
        entry['end'] = component['DTEND'].dt.isoformat()
        entry['timestamp'] = component['DTSTAMP'].dt.isoformat()
        entry['url'] = component['URL']
        entry['id'] = unicode(component['UID'])
        entries.append(entry)
    return simplejson.dumps({'items': entries}, indent=4)


