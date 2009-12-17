# Test akara.dist.setup()
import sys
import os
import tempfile
import subprocess
import shutil

from akara import dist

class SetupException(Exception):
    pass

# Do a bit of extra work since nosetests might run in the top-level
# Akara directory or in test/ .
dirname = os.path.dirname(__file__)
setup_scripts_dir = os.path.join(dirname, "setup_scripts")
assert os.path.isdir(setup_scripts_dir), setup_scripts_dir

def call_setup(args):
    p = subprocess.Popen([sys.executable] + args,
                         stdout = subprocess.PIPE,
                         stderr = subprocess.STDOUT,
                         cwd=setup_scripts_dir)
    stdout = p.stdout.read()
    p.wait()
    if p.returncode != 0:
        raise SetupException("setup.py failure %d: %s" % (p.returncode, stdout,))
    # print here to help in case of failures;
    # nosetests prints captured stdout
    print stdout

def test_basic():
    dirname = tempfile.mkdtemp(prefix="akara_setup_test_")
    try:
        call_setup(["setup_basic.py", "install",
                    "--root", dirname,
                    "--akara-modules-dir", dirname])
        assert os.path.exists(os.path.join(dirname, "blah.py"))
    finally:
        shutil.rmtree(dirname)
    
def test_missing():
    try:
        call_setup(["setup_missing.py", "install",
                    "--root", "/../this/does/not/exist",
                    "--akara-modules-dir", "/../this/does/not/exist"])
        raise AssertionError
    except SetupException, err:
        s = str(err)
        assert "you need to include the 'akara_extensions' parameter" in s, s


def test_bad_ext():
    try:
        call_setup(["setup_bad_ext.py", "install",
                    "--root", "/../this/does/not/exist",
                    "--akara-modules-dir", "/../this/does/not/exist"])
        raise AssertionError
    except SetupException, err:
        s = str(err)
        assert "Akara extensions must end with '.py'" in s, s

def test_specifying_config():
    dirname = tempfile.mkdtemp(prefix="akara_setup_test_")
    config_filename = os.path.join(dirname, "akara.conf")
    try:
        f = open(config_filename, "w")
        f.write("[global]\nServerRoot = %s/blather\n" % dirname)
        f.close()
            
        call_setup(["setup_basic.py", "install",
                    "--root", dirname,
                    "--akara-config", config_filename])
        assert os.path.exists(os.path.join(dirname, "blather", "modules", "blah.py"))
    finally:
        shutil.rmtree(dirname)

# dirname has priority
def test_specifying_config_and_dir():
    dirname = tempfile.mkdtemp(prefix="akara_setup_test_")
    try:
        try:
            call_setup(["setup_basic.py", "install",
                        "--root", dirname,
                        "--akara-config", "setup_akara.conf",
                        "--akara-modules-dir", dirname])
            assert os.path.exists(os.path.join(dirname, "blah.py"))
        except SetupException, err:
            s = str(err)
            assert "flapdoodle" in s, s
    finally:
        shutil.rmtree(dirname)
