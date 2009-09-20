# -*- encoding: utf-8 -*-
'''
See also:
'''

import re, os, time
import sets
import calendar
from cStringIO import StringIO
from datetime import *; from dateutil.relativedelta import *
#from cgi import parse_qs
from itertools import *

from dateutil.parser import parse

import amara

from akara.services import simple_service, response

from string import Template

CAL_TEMPLATE = Template('''
<table class="bcCalendar" xmlns="http://www.w3.org/1999/xhtml">
  <thead>
    <tr class="bcCalendarTopHeaders">
      $prevmonth<th colspan="5">$monthname, $year</th>$nextmonth
    </tr>
    <tr class="bcCalendarWeekHeaders">
      $dayheaders
    </tr>
  </thead>
  <tbody>
    $month
  </tbody>
</table>
''')

SERVICE_ID = 'http://purl.org/akara/services/builtin/calendar'
@simple_service('GET', SERVICE_ID, 'akara.calendar', 'text/html')
def akara_calendar(): #year=0, month=0, day=0
    '''
    Return a calendar in HTML
    Generates a calendar along the lines of:

        <  January, 2007   >
        Mo Tu We Th Fr Sa Su
               1  2  3  4  5
         6  7  8  9 10 11 12
        13 14 15 16 17 18 19
        20 21 22 23 24 25 26
        27 28 29 30 31

    Marks present date and those that have entries with archive links

    Defines the following classes (for use in CSS customization):

      - bcCalendar
        - calendar table (note: month/year header e.g. January 2007 is in table/th)
      - bcCalendarWeekHeaders
        - week header (Su, Mo, Tu, ...)
      - bcCalendarEmpty
        - filler cell (e.g. days after Jan 31)
      - bcCalendarLive
        - day for which there is an entry (also has links to that day's archives)

    And the following IDs:

      - bcCalendarToday
        - today's calendar day
      - bcCalendarSpecificDay
        - specific day being rendered (if any)

    Some ideas (e.g. CSS styling of the table) from pycalendar.py by Will Guaraldi

    Sample request:
    curl http://localhost:8880/akara.calendar
    '''

    #year, month, day = tuple([
    #    int(req.urlvars.get('year', '0')),
    #    int(req.urlvars.get('month', '0')),
    #    int(req.urlvars.get('day', '0')),
    #])
    today = date.today()
    specific_day = today.day
    #specific_day = day
    #if not (year and month and day):
    #    year, month, day = today.year, today.month, today.day
    year, month, day = today.year, today.month, today.day

    dayheaders = ''.join(
        ['<td>%s</td>' % dh
         for dh in calendar.weekheader(3).split()]
    )
    monthcal = calendar.monthcalendar(year, month)
    c = []
    for wk in monthcal:
        c.append('<tr>\n')
        for d in wk:
            d_int = int(d)
            attrs = ''
            if d_int < 1:
                d = '&#160;'
                fulldate = date.max #never to be found in archives
                attrs += ' class="bcCalendarEmpty"'
            else:
                fulldate = date(year, month, d_int)
            # "today" trumps "specific day"
            if d_int == today.day:
                attrs += ' id="bcCalendarToday"'
            elif d_int == specific_day:
                attrs += ' id="bcCalendarSpecificDay"'
            #if fulldate in archives:
            #    attrs += ' class="bcCalendarLive"'
                #d = '<a href="%s%i/%i/%s/">%s</a>'%(self.weblog_base_url, year, month, d, d)
            #    d = '%s'%(d)
            c.append('\t<td%s>%s</td>\n' % (attrs, d))
        c.append('\n</tr>\n')
    monthname =  calendar.month_name[month]
    prevmonth = date(year, month, day) + relativedelta(months=-1)
    nextmonth = date(year, month, day) + relativedelta(months=+1)
    #Yes, even checking if prevmonth > today, so if someone surfs
    #3 month in the future, there will be no month nav links
    if prevmonth > today:
        prevmonth = ''
    else:
        #prevmonth = '<th><a href="%s%i/%i/">&lt;&lt;</a></th>'%(self.weblog_base_url, prevmonth.year, prevmonth.month)
        prevmonth = '<th><a href="%s%i/%i/">&lt;&lt;</a></th>'%('/', prevmonth.year, prevmonth.month)
    if nextmonth > today:
        nextmonth = ''
    else:
        nextmonth = '<th><a href="%s%i/%i/">&gt;&gt;</a></th>'%('/', nextmonth.year, nextmonth.month)
    month = ''.join(c)
    cal = CAL_TEMPLATE.safe_substitute(locals())
    #response.content_type = 'application/xhtml+xml'
    return cal

