# -*- encoding: utf-8 -*-
'''
See also:
'''

import re, os, time
import calendar
from datetime import date; from dateutil.relativedelta import *
from itertools import *
from wsgiref.util import shift_path_info, request_uri

from dateutil.parser import parse

import amara

from akara.services import simple_service
from akara import request
from akara import logger

from string import Template

CAL_TEMPLATE = Template('''
<table class="akaraCalCalendar" xmlns="http://www.w3.org/1999/xhtml">
  <thead>
    <tr class="akaraCalCalendarTopHeaders">
      $prevmonth<th colspan="5">$monthname, $year</th>$nextmonth
    </tr>
    <tr class="akaraCalCalendarWeekHeaders">
      $dayheaders
    </tr>
  </thead>
  <tbody>
    $month
  </tbody>
</table>
''')

SERVICE_ID = 'http://purl.org/xml3k/akara/services/demo/calendar'
@simple_service('GET', SERVICE_ID, 'akara.calendar', 'text/html') #application/xhtml+xml
def akara_calendar(highlight=None):
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

      - akaraCalCalendar
        - calendar table (note: month/year header e.g. January 2007 is in table/th)
      - akaraCalCalendarWeekHeaders
        - week header (Su, Mo, Tu, ...)
      - akaraCalCalendarEmpty
        - filler cell (e.g. days after Jan 31)
      - akaraCalCalendarLive
        - day for which there is an entry (also has links to that day's archives)

    And the following IDs:

      - akaraCalCalendarToday
        - today's calendar day
      - akaraCalCalendarSpecificDay
        - specific day being rendered (if any)

    Some ideas (e.g. CSS styling of the table) from pycalendar.py by Will Guaraldi

    Sample request:
    curl http://localhost:8880/akara.calendar
    curl http://localhost:8880/akara.calendar/2008/12
    curl http://localhost:8880/akara.calendar/2008/12?highlight=2008-12-03
    '''
    today = date.today()
    year = shift_path_info(request.environ)
    month = shift_path_info(request.environ)
    if highlight:
        #Fun axiom: date(*map(int, date.today().isoformat().split('-')))
        highlight = date(*map(int, highlight.split('-')))
    if year and month:
        #Use specified year & month
        year, month = int(year), int(month)
        if (year, month) == (today.year, today.month):
            present_day = today.day
        else:
            present_day = None
    else:
        #XXX We might want to return Bad Request of they specified year but not day
        #Use present year & month
        year, month = today.year, today.month
        present_day = today.day
    #logger.debug("year: " + repr(year))

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
                attrs += ' class="akaraCalCalendarEmpty"'
            else:
                fulldate = date(year, month, d_int)
            # "today" trumps "specific day"
            if d_int == present_day:
                attrs += ' id="akaraCalCalendarToday"'
            elif highlight and d_int == highlight.day:
                attrs += ' id="akaraCalCalendarSpecificDay"'
            #if fulldate in archives:
            #    attrs += ' class="akaraCalCalendarLive"'
                #d = '<a href="%s%i/%i/%s/">%s</a>'%(self.weblog_base_url, year, month, d, d)
            #    d = '%s'%(d)
            c.append('\t<td%s>%s</td>\n' % (attrs, d))
        c.append('\n</tr>\n')
    monthname =  calendar.month_name[month]
    prevmonth = date(year, month, 1) + relativedelta(months=-1)
    nextmonth = date(year, month, 1) + relativedelta(months=+1)
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
    return cal

