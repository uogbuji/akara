"""
Atom output

Based on:
    
    RSS Handling

    @copyright: 2006-2007 MoinMoin:ThomasWaldmann
    @license: GNU GPL, see COPYING for details.
"""
import re, time
from MoinMoin import config, wikiutil
from MoinMoin.logfile import editlog
from MoinMoin.util import timefuncs
from MoinMoin.Page import Page
from MoinMoin.wikixml.util import RssGenerator

from amara.writers.struct import structencoder, E, E_CURSOR, NS, ROOT, RAW
from amara.namespaces import ATOM_NAMESPACE

RSSWIKI_NAMESPACE = u"http://purl.org/rss/1.0/modules/wiki/"

def full_url(request, page, querystr=None, anchor=None):
    url = page.url(request, anchor=anchor, querystr=querystr)
    url = wikiutil.escape(url)
    return request.getQualifiedURL(url)

def execute(pagename, request):
    """ Send recent changes as an RSS document
    """
    cfg = request.cfg

    # get params
    items_limit = 100
    try:
        max_items = int(request.values['items'])
        max_items = min(max_items, items_limit) # not more than `items_limit`
    except (KeyError, ValueError):
        # not more than 15 items in a RSS file by default
        max_items = 15
    try:
        unique = int(request.values.get('unique', 0))
    except ValueError:
        unique = 0
    try:
        diffs = int(request.values.get('diffs', 0))
    except ValueError:
        diffs = 0
    ## ddiffs inserted by Ralf Zosel <ralf@zosel.com>, 04.12.2003
    try:
        ddiffs = int(request.values.get('ddiffs', 0))
    except ValueError:
        ddiffs = 0

    urlfilter = request.values.get('filter')
    if urlfilter:
        urlfilter = re.compile(urlfilter)
    else:
        urlfilter = None

    # get data
    log = editlog.EditLog(request)
    logdata = []
    counter = 0
    pages = {}
    lastmod = 0
    for line in log.reverse():
        if urlfilter and not(urlfilter.match(line.pagename)):
            continue
        if not request.user.may.read(line.pagename):
            continue
        if (not line.action.startswith('SAVE') or
            ((line.pagename in pages) and unique)): continue
        #if log.dayChanged() and log.daycount > _MAX_DAYS: break
        line.editor = line.getInterwikiEditorData(request)
        line.time = timefuncs.tmtuple(wikiutil.version2timestamp(line.ed_time_usecs)) # UTC
        logdata.append(line)
        pages[line.pagename] = None

        if not lastmod:
            lastmod = wikiutil.version2timestamp(line.ed_time_usecs)

        counter += 1
        if counter >= max_items:
            break
    del log

    timestamp = timefuncs.formathttpdate(lastmod)
    etag = "%d-%d-%d-%d-%d" % (lastmod, max_items, diffs, ddiffs, unique)

    # for 304, we look at if-modified-since and if-none-match headers,
    # one of them must match and the other is either not there or must match.
    if request.if_modified_since == timestamp:
        if request.if_none_match:
            if request.if_none_match == etag:
                request.status_code = 304
        else:
            request.status_code = 304
    elif request.if_none_match == etag:
        if request.if_modified_since:
            if request.if_modified_since == timestamp:
                request.status_code = 304
        else:
            request.status_code = 304
    else:
        # generate an Expires header, using whatever setting the admin
        # defined for suggested cache lifetime of the RecentChanges RSS doc
        expires = time.time() + cfg.rss_cache

        request.mimetype = 'application/rss+xml'
        request.expires = expires
        request.last_modified = lastmod
        request.headers['Etag'] = etag

        # send the generated XML document
        baseurl = request.url_root

        logo = re.search(r'src="([^"]*)"', cfg.logo_string)
        if logo:
            logo = request.getQualifiedURL(logo.group(1))

        # prepare output
        output = structencoder(indent=u"yes")

        FEED_HEADER_COMMENT = '''
<!--
    Add an "items=nnn" URL parameter to get more than the default 15 items.
    You cannot get more than %d items though.
    
    Add "unique=1" to get a list of changes where page names are unique,
    i.e. where only the latest change of each page is reflected.
    Add "diffs=1" to add change diffs to the description of each items.
    
    Add "ddiffs=1" to link directly to the diff (good for FeedReader).
    Current settings: items=%i, unique=%i, diffs=%i, ddiffs=%i
-->
        ''' % (items_limit, max_items, unique, diffs, ddiffs)

        # Feed envelope
        page = Page(request, pagename)
        f = output.cofeed(
            ROOT(
                NS(u'', ATOM_NAMESPACE),
                NS(u'wiki', RSSWIKI_NAMESPACE),
                E_CURSOR((ATOM_NAMESPACE, u'feed'),
              )
            )
        )
        f.send(E((ATOM_NAMESPACE, u'id'), full_url(request, page).encode(config.charset))),
        f.send(E((ATOM_NAMESPACE, u'title'), cfg.sitename.encode(config.charset))),
        f.send(E((ATOM_NAMESPACE, u'link'), {u'href': request.url_root.encode(config.charset)})),
        f.send(E((ATOM_NAMESPACE, u'summary'), ('RecentChanges at %s' % cfg.sitename).encode(config.charset))),
        #Icon
        #E((ATOM_NAMESPACE, u'link'), {u'href': logo.encode(config.charset)}),

        #if cfg.interwikiname:
        #    handler.simpleNode(('wiki', 'interwiki'), cfg.interwikiname)

        for item in logdata:
            anchor = "%04d%02d%02d%02d%02d%02d" % item.time[:6]
            page = Page(request, item.pagename)
            #link = full_url(request, page, anchor=anchor)
            if ddiffs:
                link = full_url(request, page, querystr={'action': 'diff'})
            else:
                link = full_url(request, page)

            # description
            desc_text = item.comment
            if diffs:
                # TODO: rewrite / extend wikiutil.pagediff
                # searching for the matching pages doesn't really belong here
                revisions = page.getRevList()

                rl = len(revisions)
                for idx in range(rl):
                    rev = revisions[idx]
                    if rev <= item.rev:
                        if idx + 1 < rl:
                            lines = wikiutil.pagediff(request, item.pagename, revisions[idx+1], item.pagename, 0, ignorews=1)
                            if len(lines) > 20:
                                lines = lines[:20] + ['...\n']
                            lines = '\n'.join(lines)
                            lines = wikiutil.escape(lines)
                            desc_text = '%s\n<pre>\n%s\n</pre>\n' % (desc_text, lines)
                        break
            #if desc_text:
            #    handler.simpleNode('description', desc_text)

            # contributor
            edattr = {}
            #if cfg.show_hosts:
            #    edattr[(handler.xmlns['wiki'], 'host')] = item.hostname
            if item.editor[0] == 'interwiki':
                edname = "%s:%s" % item.editor[1]
                ##edattr[(None, 'link')] = baseurl + wikiutil.quoteWikiname(edname)
            else: # 'ip'
                edname = item.editor[1]
                ##edattr[(None, 'link')] = link + "?action=info"

            history_link = full_url(request, page, querystr={'action': 'info'})

            f.send(
                E((ATOM_NAMESPACE, u'entry'),
                    E((ATOM_NAMESPACE, u'id'), link.encode(config.charset)),
                    E((ATOM_NAMESPACE, u'title'), item.pagename.encode(config.charset)),
                    E((ATOM_NAMESPACE, u'updated'), timefuncs.W3CDate(item.time).encode(config.charset)),
                    E((ATOM_NAMESPACE, u'link'), {u'href': link.encode(config.charset)}),
                    E((ATOM_NAMESPACE, u'summary'), desc_text.encode(config.charset)),
                    E((ATOM_NAMESPACE, u'author'),
                        E((ATOM_NAMESPACE, u'name'), edname.encode(config.charset))
                    ),
                    #E((ATOM_NAMESPACE, u'title'), item.pagename.encode(config.charset)),
                    # wiki extensions
                    E((RSSWIKI_NAMESPACE, u'wiki:version'), ("%i" % (item.ed_time_usecs)).encode(config.charset)),
                    E((RSSWIKI_NAMESPACE, u'wiki:status'), (u'deleted', u'updated')[page.exists()]),
                    E((RSSWIKI_NAMESPACE, u'wiki:diff'), link.encode(config.charset)),
                    E((RSSWIKI_NAMESPACE, u'wiki:history'), history_link.encode(config.charset)),
                    # handler.simpleNode(('wiki', 'importance'), ) # ( major | minor )
                    # handler.simpleNode(('wiki', 'version'), ) # ( #PCDATA )
                )
            )

        # emit logo data
        #if logo:
        #    handler.startNode('image', attr={
        #        (handler.xmlns['rdf'], 'about'): logo,
        #        })
        #    handler.simpleNode('title', cfg.sitename)
        #    handler.simpleNode('link', baseurl)
        #    handler.simpleNode('url', logo)
        #    handler.endNode('image')

        f.close()
        request.write(output.read())

