#akara.resource
"""
There is no superclass for an Akara resource.  It's any object with an id data mamber

self.policy - instance of L{akara.policy.manager}

"""

__all__ = ['manager']

class manager(dict):
    """
    Manager itself is a very simple dict interface.  You would generally use a more specialized
    object that includes the persistence layer
    """
    def __init__(self, input_dict = {}):
        dict.__init__(self)
        self.update(input_dict)



