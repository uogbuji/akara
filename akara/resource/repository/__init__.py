#akara.resource.repository
"""

"""
import sqlite3
from cStringIO import StringIO


#__all__ = ['driver']

class driver(object):
    """
    Typical usage:
    
    driver = akara.resource.repository.driver(sqlite3.connect(conn_str))
    """
    def __init__(self, conn):
        self._conn = conn
        pass

    def create_resource(self, content, metadata):
        """
        content - the actual content of the resource
        metadata - a dictionary

        We will generate the id.
        If e.g. they use hierarchical path aliases, that would be part of the metadata
        """
        c = self._conn.cursor()
        #http://www.sqlite.org/faq.html#q1
        c.execute('INSERT into resources values(NULL, ?)', (content,))
        new_id = c.lastrowid
        #c.execute('SELECT max(id) FROM resources')
        #rowid = c.next()[0]
        #print 'past inserted', rowid
        #Use executemany?
        for key, value in metadata.iteritems():
            c.execute('insert into metadata values(?, ?, ?)', (new_id, key, value))
        self._conn.commit()
        return new_id

    def has_resource(self, id):
        """
        id = ID of the resource to check
        
        Return a boolean
        """
        c = self._conn.cursor()
        c.execute('select content from resources where id=?', (id,))
        try:
            c.next()
            resource_exists = True
        except:
            resource_exists = False
        c.close()
        return resource_exists

    def get_resource(self, id):
        """
        id = ID of the resource to get
        
        return a stream and an iterator over the metadata dict
        """
        c = self._conn.cursor()
        c.execute('select content from resources where id=?', (id,))
        data = c.fetchone()
        if not data:
            c.close()
            return None, None
        data = data[0]
        c.execute('select key, value from metadata where id=?', (id,))
        metadata = dict(c)
        #for row in c:
        c.close()
        #stream = StringIO(data)
        return data, metadata

    def update_resource(self, id, content=None, metadata=None):
        """
        id - ID of the resource to update
        content - text or stream with new resource content, or None to leave content untouched
        metadata - dict of metadata to be added/updated
        
        return a stream and an iterator over the metadata dict
        """
        c = self._conn.cursor()
        if content is not None:
            c.execute('update resources set content=? where id=?', (content, id))
        #Use executemany?
        for key, value in metadata.iteritems():
            c.execute('update metadata set key=?, set value=? where id=?', (key, value, id,))
        self._conn.commit()
        return

    def delete_resource(self, id):
        """
        id = ID of the resource to delete
        """
        c = self._conn.cursor()
        c.execute('DELETE from resources where id=?', (id,))
        c.execute('DELETE from metadata where id=?', (id,))
        self._conn.commit()
        return

    def get_metadata(self, id):
        """
        id = ID of the resource to get
        
        return a stream and an iterator over the metadata dict
        """
        c = self._conn.cursor()
        #c.execute('select content from resources where id=?', (id,))
        #data = c.next()[0]
        c.execute('select key, value from metadata where id=?', (path,))
        metadata = dict(c)
        #for row in c:
        c.close()
        return metadata

    def lookup(self, key, value):
        """
        key - metadata key
        value - metadata value to match
        """
        c = self._conn.cursor()
        #c.execute('select content from resources where id=?', (id,))
        #data = c.next()[0]
        c.execute('select id from metadata where key=? and value=?', (key, value))
        result = [ r[0] for r in c ]
        #metadata = dict(c)
        #for row in c:
        c.close()
        return result

    def orderby(self, key, count=None, reverse=False):
        """
        id = ID of the resource to get
        
        return a stream and an iterator over the metadata dict
        """
        direction = 'DESC' if reverse else 'ASC'
        c = self._conn.cursor()
        #c.execute('select content from resources where id=?', (id,))
        #data = c.next()[0]
        if count:
            c.execute('select id, value from metadata where key=? order by value %s limit ?'%(direction), (key, count))
        else:
            c.execute('select id, value from metadata where key=? order by value %s'%(direction), (key,))
        result = [ r[0] for r in c ]
        #metadata = dict(c)
        #for row in c:
        c.close()
        return result

    #def create_alias(self, alias, id):
    #    """
    #    alias - the alias for the resource
    #    id - the resource's ID
    #    """
    #    c = self._conn.cursor()
    #    c.execute('INSERT into alias values(?, ?)', (alias, id))
    #    self._conn.commit()
    #    #def lookup_alias(self, alias):
    #    #c.execute('SELECT * from alias values(?, ?)', (alias, id))
    #    return new_id

    @staticmethod
    def init_db(conn):
        c = conn.cursor()

        # Create table
        c.execute('''create table resources
        (id INTEGER PRIMARY KEY, content TEXT)''')
        c.execute('''create table metadata
        (id INTEGER, key TEXT, value TEXT)''')
        #c.execute('''create table aliases
        #(alias TEXT, id INTEGER)''')
        
        c.close()
        pass


