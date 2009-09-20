# -*- encoding: utf-8 -*-
'''
Requires http://pypi.python.org/pypi/icalendar/
easy_install icalendar
'''

import urllib2

import simplejson

# Top-level import errors cause an infinite loop problem (see trac #6)
# If this third-party package doesn't exist, report the problem but
# keep on going.
try:
    from icalendar import Calendar, Event
except ImportError, err:
    import warnings
    warnings.warn("Cannot import 'icalendar': %s" % (err,))
    Calendar = Event = NotImplementedError

from akara.services import simple_service, response

SERVICE_ID = 'http://purl.org/akara/services/builtin/ical.json'
@simple_service('POST', SERVICE_ID, 'ical.json', 'application/json')
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
        entry['start'] = component['DTSTART'].dt.isoformat()
        entry['end'] = component['DTEND'].dt.isoformat()
        if "URL" in component:
            entry['url'] = component['URL']
        # These are Outlook specific(?)
        if "DESCRIPTION" in component:
            entry['description'] = unicode(component['DESCRIPTION'])
        if "UID" in component:
            entry['id'] = unicode(component['UID'])
        if "DTSTAMP" in component:
            entry['timestamp'] = component['DTSTAMP'].dt.isoformat()

        entries.append(entry)
    return simplejson.dumps({'items': entries}, indent=4)


