# -*- encoding: utf-8 -*-
'''
@ 2009 by Uche ogbuji <uche@ogbuji.net>

This file is part of the open source Akara project,
provided under the Apache 2.0 license.
See the files LICENSE and NOTICE for details.
Project home, documentation, distributions: http://wiki.xml3k.org/Akara

 Module name:: echo
 
Responds to POST with the same body content as sent in the request

= Defined REST entry points =

http://purl.org/akara/services/demo/echo (akara.echo) Handles POST

= Configuration =

No configuration required

= Notes on security =

This module only sends information available in the request.  No security implications.
'''

import amara
from akara.services import simple_service

ECHO_SERVICE_ID = 'http://purl.org/xml3k/akara/services/demo/echo'


@simple_service('POST', ECHO_SERVICE_ID, 'akara.echo')
def akara_echo_body(body, ctype, log=u'no'):
    '''
    Sample request:
    curl --request POST --data-binary "@foo.dat" --header "Content-type: text/plain" "http://localhost:8880/akara.echo"
    '''
    if log == u'yes':
        from akara import logger
        logger.debug('akara_echo_body: ' + body)
    return body

