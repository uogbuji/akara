"""Support code for dealing with distutils and (eventually) Distribute.

"""
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
            self.akara_config = None
            self.akara_modules_dir = None

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
