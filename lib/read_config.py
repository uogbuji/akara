"""Parse the Akara config file (in .ini format) and get system settings from it

This is an internal module and should not be used by other libraries.

"""
import os
import logging
import ConfigParser

class Error(Exception):
    pass

DEFAULT_SERVER_CONFIG_FILE = os.path.expanduser('~/.config/akara.conf')

SERVER_CONFIG_DEFAULTS = {
    'global': {
        'Listen': '8880',
        'ServerRoot': '~/.local/lib/akara',
        'PidFile': 'logs/akara.pid',

        'MinSpareServers': '5',
        'MaxSpareServers': '10',
        'MaxServers': '150',
        'MaxRequestsPerServer': '10000',

        'ModuleDir': 'modules',
        'ErrorLog': 'logs/error.log',
        'AccessLog': 'logs/access.log',
        'LogLevel': 'INFO',
        },
    'akara.cache': {
        'DefaultExpire': '3600',
        'LastModifiedFactor': '0.1',
        },
    }


_valid_log_levels = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARN": logging.WARN,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
    }


log = logging.getLogger("akara.server")

def _add_config_defaults(config):
    # in-place modify the config
    for section, defaults in SERVER_CONFIG_DEFAULTS.iteritems():
        if not config.has_section(section):
            config.add_section(section)
        for name, value in defaults.iteritems():
            if not config.has_option(section, name):
                config.set(section, name, value)
    return config

def read_config(config_file=None):
    "Read an Akara .ini config file and return the parsed settings and the ConfigParser"""
    if config_file is None:
        config_file = DEFAULT_SERVER_CONFIG_FILE
    config = ConfigParser.ConfigParser()
    config_file_exists = True
    try:
        f = open(config_file)
    except IOError, err:
        log.warning("""\
Could not open Akara configuration file: %s
Using default configuration settings. 
To set up the default configuration file and directories use
  akara setup
""" % (err,))
        config_file_exists = False

    try:
        if config_file_exists:
            config.readfp(f)
            # Do some sanity checks. It's best to do these tests now because
            # doing them downstream leads to more confusing error messages.
            if not config.sections():
                raise Error("Configuration file is empty")
            if not config.has_section("global"):
                raise Error("Configuration file missing required 'global' section")
        _add_config_defaults(config)
        settings = _extract_settings(config)
    except (Error, ConfigParser.Error), err:
        raise Error("Could not read from Akara configuration file %r: %s" %
                    (config_file, err))
    return settings, config
        

def _extract_settings(config):
    """Get parsed setting information from a config object

    This does sanity checking on the input (like that port numbers
    must be positive integers) and converts things into the
    appropriate data type (like integers).
    """
    settings = {}

    # The value for 'Listen' can be:
    #    <port> as in "8080"
    # -or-
    #    <host>:<port> as in "localhost:8081"
    addr = config.get('global', 'Listen')
    if ':' in addr:
        host, port_s = addr.rsplit(':', 1)
    else:
        host, port_s = '', addr
    try:
        port = int(port_s)
        if port <= 0:
            raise ValueError
    except ValueError:
        raise Error("Listen port must be a positive integer, not %r" % port_s)

    settings["server_address"] = (host, port)

    server_root = config.get('global', 'ServerRoot')
    server_root = os.path.expanduser(server_root)
    settings["server_root"] = os.path.abspath(server_root)

    pid_file = config.get('global', 'PidFile')
    settings["pid_file"] = os.path.join(server_root, pid_file)

    error_log = config.get('global', 'ErrorLog')
    settings["error_log"] = os.path.join(server_root, error_log)

    access_log = config.get('global', 'AccessLog')
    settings["access_log"] = os.path.join(server_root, access_log)

    module_dir = config.get("global", "ModuleDir")
    settings["module_dir"] = os.path.join(server_root, module_dir)

    log_level_orig = config.get('global', 'LogLevel')
    log_level_s = log_level_orig.upper()
    if log_level_s in _valid_log_levels:
        log_level = _valid_log_levels[log_level_s]
    else:
        raise Error(
            "global setting 'LogLevel' is %r but must be one of: %s" %
            (log_level_s, ", ".join(map(repr, _valid_log_levels))))
                    
    settings["log_level"] = log_level


    # Some helper functions to numeric fields with better error
    # reporting than calling 'getint' directly.
    def getint(section, option):
        try:
            return config.getint(section, option)
        except ValueError:
            raise Error("Option %r in section %r must be an integer, not %r" % 
                        (option, section, item))
        
    def getpositive(section, option):
        value = getint(section, option)
        if value <= 0:
            raise Error(
                "Option %r in section %r must be a positive integer: %r" %
                (option, section, item))
        return value

    def getnonnegative(section, option):
        value = getint(section, option)
        if value < 0:
            raise Error(
                "Option %r in section %r must be a positive integer or 0: %r" %
                (option, section, item))
        return value

    settings["max_servers"] = getpositive('global', 'MaxServers')
    settings["min_spare_servers"] = getnonnegative('global', 'MinSpareServers')
    settings["max_spare_servers"] = getnonnegative('global', 'MaxSpareServers')
    if settings["max_spare_servers"] < settings["min_spare_servers"]:
        raise Error("MaxSpareServers (%r) must be greater than MinSpareServers (%r)" %
                    (settings["max_spare_servers"], settings["min_spare_servers"]))
    settings["max_requests_per_server"] = getpositive('global', 'MaxRequestsPerServer')

    return settings

