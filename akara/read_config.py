import os
import logging
import ConfigParser

class Error(Exception):
    pass

DEFAULT_SERVER_CONFIG_FILE = os.path.expanduser('~/.config/akara.conf')

SERVER_CONFIG_DEFAULTS = {
    'global': {
        # 'Listen': passed in
        'ServerRoot': '~/.local/lib/akara', # must be present
        'PidFile': 'logs/akara.pid',  # must be present

        'StartServers': '5',
        'MinSpareServers': '5',
        'MaxSpareServers': '10',
        'MaxServers': '150',
        'MaxRequestsPerServer': '10000',

        'ModuleDir': 'modules',
        'ErrorLog': 'logs/error.log',  # must be present
        'LogLevel': 'notice',  # must be present
        'AccessLog': '',
        },
    'akara.cache': {
        'DefaultExpire': '3600',
        'LastModifiedFactor': '0.1',
        },
    }

# The Akara levels were:
#   emerg, alert, crit, error, warn, notice, info, debug
# but these did not have any real definition. I'll map these
# to the Python logging levels as:
_backwards_compatible_levels = {
    "emerg": "CRITICAL",
    "alert": "CRITICAL",
    "crit": "CRITICAL",
    "error": "ERROR",
    "warn": "WARN",
    "notice": "INFO",
    "info": "INFO",
    "debug": "DEBUG",
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

def _init_config_defaults():
    config = ConfigParser.ConfigParser()
    for section, defaults in SERVER_CONFIG_DEFAULTS.iteritems():
        config.add_section(section)
        for name, value in defaults.iteritems():
            config.set(section, name, value)
    return config

def read_config(config_file=None):
    if config_file is None:
        config_file = DEFAULT_SERVER_CONFIG_FILE
    config = _init_config_defaults()
    try:
        f = open(config_file)
    except IOError, err:
        raise Error("Could not open Akara configuration file: %s" % (err,))
    try:
        config.readfp(f)
        settings = _extract_settings(config)
    except (Error, ConfigParser.Error), err:
        raise Error("Could not read from Akara configuration file %r: %s" %
                    (config_file, err))
    return settings, config
        

def _extract_settings(config):
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

    module_dir = config.get("global", "ModuleDir")
    settings["module_dir"] = os.path.join(server_root, module_dir)

    log_level_orig = config.get('global', 'LogLevel')
    log_level_s = log_level_orig.upper()
    if log_level_s in _valid_log_levels:
        log_level = _valid_log_levels[log_level_s]
    else:
        # Perhaps one of the backwards compatible levels?
        log_level_s = log_level_orig.lower()
        if log_level_s in _backwards_compatible_levels:
            log_level = _valid_log_levels[_backwards_compatible_levels[log_level_s]]
        else:
            raise Error(
                "global setting 'LogLevel' is %r but must be one of: %s" %
                (log_level, ", ".join(map(repr, _valid_log_levels))))
                    
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

    settings["start_servers"] = getpositive('global', 'StartServers')
    settings["max_servers"] = getpositive('global', 'MaxServers')
    settings["min_spare_servers"] = getnonnegative('global', 'MinSpareServers')
    settings["max_spare_servers"] = getnonnegative('global', 'MaxSpareServers')
    if settings["max_spare_servers"] < settings["min_spare_servers"]:
        raise Error("MaxSpareServers (%r) must be greater than MinSpareServers (%r)" %
                    (settings["max_spare_servers"], settings["min_spare_servers"]))
    settings["max_requests_per_server"] = getpositive('global', 'MaxRequestsPerServer')

    return settings

