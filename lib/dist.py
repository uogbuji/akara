"""Support code for dealing with distutils and (eventually) Distribute.

This is a helper module for installing Akara extensions. It extends
the standard distutils installer. Please read 
  http://docs.python.org/distutils/
for a detailed description of how to use and distribute software
packages with distutils.

This version of setup() supports the "akara_extensions" option, which
is a list of Python files to install into the Akara extension module
directory. Your setup.py file might look like this:

  from akara.dist import setup

  setup(name = "MyAkaraExtension",
        version = "9.8",
        description = "An example Akara extension",
        akara_extensions = ["module1.py", "module2.py"],
        )

and here is an example of it in use:

  % python setup.py install


All of the normal distutils options, like the ability to install
Python modules, C-based extensions, and data files, are still
available. This does mean that all packages will create an egg, even
if no other Python code is installed.

The Akara extension directory is not a versioned directory. Extensions
placed in that directory are not managed by the Python egg system and
will not work under virtualenv or similar tools.

The default extension directory location comes from the default Akara
configuration file. You can specify an alternate configuration file
with --akara-config, as in

  % python setup.py install --akara-config ~/my_akara.conf

or specify the installation directory direclty with
--akara-modules-dir, as in

  % python setup.py install --akara-modules-dir ~/local/modules

"""
import os
import shutil

from distutils.core import setup as _setup
from distutils.core import Command
from distutils import log

# Has not been tested against setuptools or Distribute and probably
# won't work with them.
# Let the Akara development team know if that's a problem.

from distutils.command.install import install as old_install
from distutils.dist import Distribution as _Distribution

import akara.read_config


MISSING_AKARA_EXTENSIONS = (
"If you call the Akara setup adapter for distutils.core.setup then\n"
"you need to include the 'akara_extensions' parameter, which is a\n"
"list of one or more filenames ending with '.py'")

EXTENSION_OPTIONS = [
    ("akara-config=", None,
     ("Location of an existing akara.conf use to get the 'modules' directory "
      "if --akara-modules-dir is not specified")),
    ("akara-modules-dir=", None,
     ("Directory in which to place the new Akara extension and configuration files. "
      "If not specified, get it from akara.conf")),
    ]


def setup(**kwargs):
    if "akara_extensions" not in kwargs:
        raise SystemExit(MISSING_AKARA_EXTENSIONS)
    for filename in kwargs["akara_extensions"]:
        if not filename.endswith(".py"):
            raise SystemExit(
                "Akara extensions must end with '.py' not %r" %
                (filename,))
    for filename in kwargs.get("akara_extension_confs", []):
        if not filename.endswith(".conf"):
            raise SystemExit(
                "Akara extension configuration files must end with '.conf' not %r" %
                (filename,))

    new_kwargs = kwargs.copy()

    # Create our new installation code.
    # Figure out which command class to wrap.
    cmdclass = new_kwargs.get('cmdclass', {})
    if 'install' in cmdclass:
        install = cmdclass['install']
    else:
        install = old_install

    # A hook to add our own extensions
    class my_install(install):
        sub_commands = install.sub_commands + [
                ('install_akara_extensions', None)
        ]
        user_options = install.user_options + EXTENSION_OPTIONS
        def initialize_options(self):
            install.initialize_options(self)
            self.akara_config = None
            self.akara_modules_dir = None


    # Our installation extension
    class install_akara_extensions(Command):
        description = "Command to install akara extensions"

        user_options = EXTENSION_OPTIONS

        def initialize_options(self):
            # I so don't know what I'm doing here, but it seems to work.
            args =  self.distribution.command_options["install"]
            self.akara_modules_dir = self.akara_config = None
            for key, value in args.items():
                if key == "akara_modules_dir":
                    self.akara_modules_dir = value[1]
                elif key == "akara_config":
                    self.akara_config = value[1]

        def finalize_options(self):
            if self.akara_modules_dir is None:
                settings, config = akara.read_config.read_config(self.akara_config)
                self.akara_modules_dir = settings["module_dir"]

        def run (self):
            dist = self.distribution
            for (description, filenames) in (
                ("extension", dist.akara_extensions),
                ("configuration", dist.akara_extension_confs)):
                for filename in filenames:
                    log.info("Installing Akara %s %r in %r" %
                             (description, filename, self.akara_modules_dir))
                    if not self.dry_run:
                        if not os.path.isdir(self.akara_modules_dir):
                            os.makedirs(self.akara_modules_dir) # Make sure the directory exists
                        shutil.copy(filename, self.akara_modules_dir)

    new_cmdclass = {}
    new_cmdclass.update(cmdclass)
    new_cmdclass['install'] = my_install
    new_cmdclass['install_akara_extensions'] = install_akara_extensions
    new_kwargs['cmdclass'] = new_cmdclass

    # Handle overriden distclass
    if 'distclass' in new_kwargs:
        Distribution = new_kwargs['distclass']
    else:
        Distribution = _Distribution
    class MyDistribution(Distribution):
        def __init__(self, attrs=None):
            for opt in ("akara_extensions",
                        "akara_extension_confs"):
                assert not hasattr(self, opt)
                setattr(self, opt, attrs.get(opt, []))

            Distribution.__init__(self, attrs)

    new_kwargs['distclass'] = MyDistribution
    return _setup(**new_kwargs)
