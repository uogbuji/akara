"""Support code for dealing with distutils and (eventually) Distribute.

"""
import os
from akara import read_config

MISSING_AKARA_EXTENSIONS = (
"If you call the Akara setup adapter for distutils.core.setup then\n"
"you need to include the 'akara_extensions' parameter, which is a\n"
"list of one or more filenames ending with '.py'")

def setup(**kwargs):
    # Must specify extensions
    if "akara_extensions" not in kwargs:
        raise SystemExit(MISSING_AKARA_EXTENSIONS)
    akara_extensions = kwargs.pop("akara_extensions")
    if isinstance(akara_extensions, basestring):
        raise SystemExit("akara_extensions must be a list of filenames, not a string")
    if not akara_extensions:
        raise SystemExit("No akara_extensions specified. Nothing to do.")
    
    # (TODO) specify extension config files 

    # Did they specify an alternate master config file?
    if "akara_config_file" in kwargs:
        akara_config_filename = kwargs.pop("akara_config_file")
    else:
        akara_config_filename = read_config.DEFAULT_SERVER_CONFIG_FILE

    try:
        settings, config = read_config.read_config(akara_config_filename)
    except read_config.Error, err:
        raise SystemExit(str(err))

    module_dir = settings["module_dir"]
    if not os.path.isdir(module_dir):
        raise SystemExit("Module directory %r does not exist" % module_dir)

    # Convert these to data files for distutils
    data_files = kwargs.setdefault("data_files", [])
    
    data_files.append( (module_dir, akara_extensions) )
    
    ## This always installs an egg. We might not want to do that if only
    # an Akara extension is installed. To do that, check that there are
    # no py_modules, packages, ext_modules, scripts, or other things to be
    # installed, then replace the "install_egg_info" command class.
    #kwargs["cmdclass"] = cmdclass = {}
    #cmdclass["install_egg_info"] = ....some class ...

    from distutils.core import setup
    setup(**kwargs)
