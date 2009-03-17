########################################################################
# akara.restwrap
"""
Wrappers of tools and services made available through REST conventions

Copyright 2009 Uche Ogbuji
This file is part of the open source Akara project,
provided under the Apache 2.0 license.
See the files LICENSE and NOTICE for details.
Project home, documentation, distributions: http://wiki.xml3k.org/Akara
"""
#Detailed license and copyright information: http://4suite.org/COPYRIGHT

class simple_service(object):
    '''
    A REST wrapper that turns the keyword parameters of a function from GET params 
    '''
    def __init__(self, service_id, service_tag):
        self.service_id = service_id
        #test if type(test) in (list, tuple) else [test]
        self.service_tag = service_tag

    def __call__(self, func):
        def rest_wrapper(environ, start_response):
            response_body = func(**kwargs)
            #response = Response()
            #response.content_type = 'application/json'
            #response.body = simplejson.dumps({'items': entries}, indent=4)
            return response(environ, start_response)
        return func


def mount(funcs):
    '''
    Mount the functions on the Web
    '''
    pass


def ical2json_app(environ, start_response):
    ids = sets.Set()
    req = Request(environ)
    entries = []
    log = environ['wsgi.errors']
    cal = Calendar.from_string(req.body)
    #[ c['UID'] for c in  cal.subcomponents if c.name == 'VEVENT' ]
    for count, component in enumerate(cal.walk()):
        if count > MAXRECORDS: break
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
    response = Response()
    response.content_type = 'application/json'
    response.body = simplejson.dumps({'items': entries}, indent=4)
    return response(environ, start_response)


