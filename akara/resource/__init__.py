#akara.resource
"""
There is no superclass for an Akara resource.  It's any object with an id data mamber

self.policy - instance of L{akara.policy.manager}

"""

#__all__ = ['manager', 'standard_index']

CREATED = 'akara:created'
UPDATED = 'akara:updated'
CONTENT_LENGTH = 'akara:size'
CONTENT_TYPE = 'akara:type'

class resource(object):
    '''
    An analogue of a Web resource
    
    In effect it serves as a cache of the actual stored repository data
    
    Standard repository metadata:
    
    * Content type (internet media type)
    * Size
    * creation date
    * last mod date
    '''
    def __init__(self, rid, manager):
        self._manager = manager
        self.rid = rid
        self._metadata = None #Mixes/caches repository metadata and user metadata
        self._content = None
        return
        
    def __getitem__(self, name):
        return self._metadata[name]

    def _get_content(self):
        if self._content is None: self._sync()
        return self._content

    def _set_content(self, c):
        if self._content is None: self._sync()
        self._content = c

    content = property(_get_content, _set_content)

    @property
    def metadata(self):
        if self._metadata is None: self._sync()
        return self._metadata

    def _sync(self):
        '''
        Sync up this copy with the database
        '''
        drv = self._manager._driver
        content, self.metadata = drv.get_resource(self.rid)
        self.content = content.read()
        return


class manager(dict):
    """
    Maps aliases to IDs
    
    """
    #Manager itself is a very simple dict interface.  You would generally use a more specialized
    #object that includes the persistence layer
    #def __init__(self, input_dict={}):
    #    self.update(input_dict)

    def __init__(self, driver):
        self._driver = driver
        self.aliases = {}
        #FIXME: replace with MRU
        self._cache = {}
        return

    def lookup(self, name):
        '''
        Look up resource by ID
        '''
        rid = name
        if rid in self.aliases:
            rid = self.aliases[rid]
        if rid in self._cache:
            return elf._cache[rid]
        if self._driver.has_resource(rid):
            return resource(rid, self)
        else:
            raise RuntimeError('Resource not found: %s'%str(rid))
            #raise ResourceError
        return

