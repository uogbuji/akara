# -*- coding: iso-8859-1 -*-
"""
MoinMoin - "text/xml" Formatter using Amara 2.x

@copyright: 2010 Uche Ogbuji <uche@ogbuji.net>
@license: Apache 2.0
"""

from MoinMoin.formatter import FormatterBase
from MoinMoin import config
from MoinMoin.Page import Page

from amara import tree
from amara.writers.struct import structwriter, E, NS, ROOT, RAW
from amara.bindery.html import parse as htmlparse


class Formatter(FormatterBase):
    """
    Send XML data.
    """
    def __init__(self, request, **kw):
        FormatterBase.__init__(self, request, **kw)
        self._current_depth = 1
        self._base_depth = 0
        self.in_pre = 0
        self._doc = tree.entity()
        self._curr = self._doc
        #self._writer = structwriter(indent=u"yes", encoding=config.charset)
        return

    def macro(self, macro_obj, name, args, markup=None):
        #Macro response are (unescaped) markup.  Do what little clean-up we camn, and cross fingers
        output = FormatterBase.macro(self, macro_obj, name, args, markup=markup)
        #response is Unicode
        if output:
            output_body = htmlparse(output.encode(config.charset)).html.body
            #print "macro 2", repr(output)
            self._curr.xml_append(output_body)
        return ''

    def startDocument(self, pagename):
        self._curr = tree.element(None, u's1')
        self._curr.xml_attributes[None, u'title'] = pagename.decode(config.charset)
        self._doc.xml_append(self._curr)
        return ''

    def endDocument(self):
        #Yuck! But Moin seems to insist on Unicode object result (see MoinMoin.parser.text_moin_wiki.Parser.scan)
        #print "endDocument", repr(self._doc.xml_encode(encoding=config.charset).decode(config.charset))
        return self._doc.xml_encode(encoding=config.charset).decode(config.charset)

    def _elem(self, name, on, **kw):
        if on:
            e = tree.element(None, name)
            self._curr.xml_append(e)
            self._curr = e
        elif name == self._curr.xml_local:
            self._curr = self._curr.xml_parent
        return

    def lang(self, on, lang_name):
        self._elem(u'div', on)
        self._curr.xml_attributes[None, u'lang'] = lang_name.decode(config.charset)
        return ''

    def sysmsg(self, on, **kw):
        self._elem(u'sysmsg', on)
        return ''

    def rawHTML(self, markup):
        output = htmlparse(markup).html.body.xml_encode() if markup else ''
        #print "rawHTML", repr(output)
        return output.decode(config.charset)

    def pagelink(self, on, pagename='', page=None, **kw):
        FormatterBase.pagelink(self, on, pagename, page, **kw)
        if page is None:
            page = Page(self.request, pagename, formatter=self)
        return page.link_to(self.request, on=on, **kw)

    def interwikilink(self, on, interwiki='', pagename='', **kw):
        if on:
            return '<interwiki wiki="%s" pagename="%s">' % (interwiki, pagename)
        else:
            return '</interwiki>'

    def url(self, on, url='', css=None, **kw):
        self._elem(u'jump', on)
        if css:
            self._curr.xml_attributes[None, u'class'] = css.decode(config.charset)
        return ''

    def attachment_link(self, on, url=None, **kw):
        if on:
            return '<attachment href="%s">' % (url, )
        else:
            return '</attachment>'

    def attachment_image(self, url, **kw):
        return '<attachmentimage href="%s"></attachmentimage>' % (url, )

    def attachment_drawing(self, url, text, **kw):
        return '<attachmentdrawing href="%s">%s</attachmentdrawing>' % (url, text)

    def text(self, text, **kw):
        self._curr.xml_append(tree.text(text))
        return ''

    def rule(self, size=0, **kw):
        return "\n<br/>%s<br/>\n" % ("-" * 78, ) # <hr/> not supported in stylebook
#        if size:
#            return '<hr size="%d"/>\n' % (size, )
#        else:
#            return '<hr/>\n'

    def icon(self, type):
        return '<icon type="%s" />' % type

    def strong(self, on, **kw):
        self._elem(u'strong', on)
        return ''

    def emphasis(self, on, **kw):
        self._elem(u'em', on)
        return ''

    def highlight(self, on, **kw):
        self._elem(u'strong', on)
        return ''

    def number_list(self, on, type=None, start=None, **kw):
        self._elem(u'ol', on)
        return ''

    def bullet_list(self, on, **kw):
        self._elem(u'ul', on)
        return ''

    def listitem(self, on, **kw):
        self._elem(u'li', on)
        return ''

    def code(self, on, **kw):
        self._elem(u'code', on)
        return ''

    def small(self, on, **kw):
        self._elem(u'small', on)
        return ''

    def big(self, on, **kw):
        self._elem(u'big', on)
        return ''

    def sup(self, on, **kw):
        self._elem(u'sup', on)
        return ''

    def sub(self, on, **kw):
        self._elem(u'sub', on)
        return ''

    def strike(self, on, **kw):
        self._elem(u'strike', on)
        return ''

    def preformatted(self, on, **kw):
        FormatterBase.preformatted(self, on)
        self._elem(u'source', on)
        return ''

    def paragraph(self, on, **kw):
        FormatterBase.paragraph(self, on)
        self._elem(u'p', on)
        return ''

    def linebreak(self, preformatted=1):
        e = tree.element(None, u'br')
        self._curr.xml_append(e)
        return ''

    def heading(self, on, depth, id=None, **kw):
        # remember depth of first heading, and adapt current depth accordingly
        if not self._base_depth:
            self._base_depth = depth
        depth = max(depth + (2 - self._base_depth), 2)
        name = u's%i'%depth
        self._elem(name, on)
        id = id.decode(config.charset) if id else u''
        self._curr.xml_attributes[None, u'title'] = id
        self._curr.xml_attributes[None, u'id'] = id
        return ''

    def table(self, on, attrs={}, **kw):
        self._elem(u'table', on)
        return ''

    def table_row(self, on, attrs={}, **kw):
        self._elem(u'tr', on)
        return ''

    def table_cell(self, on, attrs={}, **kw):
        self._elem(u'td', on)
        return ''

    def anchordef(self, id):
        e = tree.element(None, u'anchor')
        self._curr.xml_append(e)
        self._curr.xml_attributes[None, u'id'] = id.decode(config.charset)
        return ''

    def anchorlink(self, on, name='', **kw):
        self._elem(u'link', on)
        id = kw.get('id', None)
        if id:
            self._curr.xml_attributes[None, u'id'] = id.decode(config.charset)
        self._curr.xml_attributes[None, u'anchor'] = name.decode(config.charset)
        return ''

    def underline(self, on, **kw):
        return self.strong(on) # no underline in StyleBook

    def definition_list(self, on, **kw):
        self._elem(u'gloss', on)
        return ''

    def definition_term(self, on, compact=0, **kw):
        self._elem(u'label', on)
        return ''

    def definition_desc(self, on, **kw):
        self._elem(u'item', on)
        return ''

    def image(self, src=None, **kw):
        e = tree.element(None, u'img')
        self._curr.xml_append(e)
        kw.update({'src': src})
        for key, value in kw.items():
            if key in valid_attrs:
                self._curr.xml_attributes[None, key.decode(config.charset)] = value.decode(config.charset)
        return ''

    def transclusion(self, on, **kw):
        # TODO, see text_html formatter
        return ''

    def transclusion_param(self, **kw):
        # TODO, see text_html formatter
        return ''

    def code_area(self, on, code_id, code_type='code', show=0, start=-1, step=-1, msg=None):
        self._elem(u'codearea', on)
        self._curr.xml_attributes[None, u'id'] = code_id.decode(config.charset)
        return ''

    def code_line(self, on):
        self._elem(u'codeline', on)
        return ''

    def code_token(self, on, tok_type):
        self._elem(u'codetoken', on)
        self._curr.xml_attributes[None, u'type'] = tok_type.decode(config.charset)
        return ''
