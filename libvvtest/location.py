#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys
from os.path import join as pjoin
from os.path import normpath, abspath, basename, dirname
import shutil
import platform

from .errors import FatalError
from . import pathutil


SCRATCH_DIR_SEARCH_LIST = [ '/scratch',
                            '/var/scratch',
                            '/var/scratch1',
                            '/scratch1',
                            '/var/scratch2',
                            '/scratch2',
                            '/var/scrl1',
                            '/gpfs1' ]


def find_sys_directory_with_file( cwd, exepath, filename ):
    ""
    for dn in sys.path + [dirname(exepath)]:

        if not abspath(dn):
            dn = pjoin( cwd, dn )

        fn = pjoin( dn, filename )

        if os.path.exists( fn ):
            return dirname( normpath(fn) )

    return None


class Locator:

    def __init__(self, idir, mirror=None, wipe=False):
        """
        'idir' is the current working directory when vvtest is initially launched
        """
        self.idir = idir

        self.mirror = mirror
        self.wipe = ( wipe == True )

        self.cashfile = None
        self.testdir = None
        self.ipath = None  # relative path from testdir to idir, or None

    def getConfigDirs(self, cmdline_configdir=None, environ_configdir=None):
        """
        A command line specification will take precedence. If it is None,
        the environment value will be used. A list of paths is returned,
        which may be empty.
        """
        return collect_config_dirs( cmdline_configdir, environ_configdir )

    def searchForCacheFile(self):
        ""
        self.cashfile = find_cache_file( self.idir )
        return self.cashfile

    def foundCacheFile(self):
        ""
        return self.cashfile is not None

    def getTestingDirectory(self):
        ""
        return self.testdir

    def setLocation(self, locdirs):
        ""
        self.testdir = normpath( dirname( self.cashfile ) )

        if locdirs:
            idir,ipath = locdirs
            if ipath is None:
                self.idir = idir
            else:
                self.idir = normpath( pjoin( self.testdir, ipath ) )
                self.ipath = ipath

    def computeLocation(self, rundir, onopts, offopts, platname):
        ""
        sd = test_results_subdir_name( rundir, onopts, offopts, platname )

        if not os.path.isabs( sd ) and not self.mirror:
            tdir = self.makeAbsPath( sd )
            self.ipath = os.path.relpath( self.idir, tdir )

        self.testdir = self.makeAbsPath( sd )

        return self.testdir

    def createTestingDirectory(self, perms):
        ""
        create_test_directory( self.testdir, self.mirror, self.idir, perms )

        if self.wipe:
            pathutil.remove_directory_contents( self.testdir )

    def makeAbsPath(self, path):
        ""
        if os.path.isabs( path ):
            return normpath( path )
        else:
            return normpath( pjoin( self.idir, path ) )

    def path_to_source(self, subdir, srcroot):
        """
        Returns the path to the test source directory. May be an absolute
        path (if both the rundir and 'srcroot' are relative paths), or a
        relative directory. The 'subdir' is a relative path from the source
        to the directory containing the test vvt file.
        """
        # print( 'magic: p2s', repr(subdir), repr(srcroot), repr(self.ipath), repr(self.idir) )
        if os.path.isabs( srcroot ):
            return normpath( pjoin( srcroot, subdir ) )
        elif self.ipath:
            # Note: The extra '..' is the final xdir segment for the test.
            #       Unfortunately, this means yet another place where the
            #       execution directory structure is encoded.
            upd = pjoin( '..', reverse_path_direction( subdir ) )
            return normpath( pjoin( upd, self.ipath, srcroot, subdir ) )
        else:
            return normpath( pjoin( self.idir, srcroot, subdir ) )

    def getLocation(self):
        ""
        return self.idir, self.ipath


def reverse_path_direction( subdir ):
    """
    for example, if subdir is 'foo/bar' then return is '../..'
    """
    assert '..' not in subdir.split( os.path.sep )
    return os.path.relpath( '/', pjoin('/',subdir) )


def find_cache_file( cwd ):
    """
    returns path to cache file if the CWD is inside a TestResults directory,
    otherwise returns None
    """
    # an environment variable is used to identify vvtest run recursion
    troot = os.environ.get( 'VVTEST_TEST_ROOT', None )

    cashfile = find_vvtest_test_root_file( cwd, troot, 'vvtest.cache' )

    if not cashfile:
        # June 2022: name changed from test.cache to vvtest.cache, but look
        #            for the old name for a while (a year?)
        # this note is also in vvtest and scanner.py
        cashfile = find_vvtest_test_root_file( cwd, troot, 'test.cache' )

    return cashfile


def find_vvtest_test_root_file( start_directory,
                                stop_directory,
                                marker_filename ):
    """
    Starting at the 'start_directory', walks up parent directories looking
    for a 'marker_filename' file.  Stops looking when it reaches the
    'stop_directory' (excluding it) or "/".  Returns None if the marker
    filename is not found.  Returns the path to the marker file if found.
    """
    stopd = None
    if stop_directory:
        stopd = normpath( stop_directory )

    d = normpath( start_directory )

    while d and d != '/':

        mf = pjoin( d, marker_filename )

        if os.path.exists( mf ):
            return mf

        d2 = dirname( d )

        if d2 == d or (stopd and d2 == stopd):
            break

        d = d2

    return None


def collect_config_dirs( opts_config, environ_config ):
    ""
    cfgL = []

    cfgspecs = []
    if opts_config:
        cfgspecs = opts_config
    elif environ_config and environ_config.strip():
        cfgspecs = [ environ_config.strip() ]

    for cfgdir in cfgspecs:
        if ':' in cfgdir:

            d1 = cfgdir
            while True:

                d1,d2 = split_by_largest_existing_path( d1 )

                if d1 == None:
                    d1,d2 = d2.split(':',1)

                if d1 != None:
                    cfgL.append( normpath( abspath(d1) ) )

                if d2 == None:
                    break
                elif ':' in d2:
                    d1 = d2
                else:
                    cfgL.append( normpath( abspath(d2) ) )
                    break

        else:
            cfgL.append( normpath( abspath( cfgdir ) ) )

    return cfgL


def split_by_largest_existing_path( path, rindex=0 ):
    ""
    if rindex == 0:
        d1 = path
        d2 = None
    else:
        pL = path.split(':')
        n = len(pL)

        if rindex >= n:
            d1 = None
            d2 = path
        else:
            d1 = ':'.join( pL[:n-rindex] )
            d2 = ':'.join( pL[n-rindex:] )

    if d1 == None or os.path.exists( d1 ):
        return d1,d2
    else:
        return split_by_largest_existing_path( path, rindex+1 )


def determine_test_directory( subdirname, test_cache_file, cwd ):
    ""
    if test_cache_file:
        assert os.path.isabs( test_cache_file )
        test_dir = normpath( dirname( test_cache_file ) )
    else:
        assert os.path.isabs( cwd )
        test_dir = normpath( pjoin( cwd, subdirname ) )

    return test_dir


def test_results_subdir_name( rundir, onopts, offopts, platform_name ):
    """
    Generates and returns the subdirectory name to hold test results, which is
    unique up to the platform and on/off options.
    """
    if rundir:
        testdirname = normpath( rundir )

    else:
        testdirname = 'TestResults.' + platform_name
        if onopts and len(onopts) > 0:
          testdirname += '.ON=' + '_'.join( onopts )
        if offopts and len(offopts) > 0:
          testdirname += '.OFF=' + '_'.join( offopts )

    return testdirname


def create_test_directory( testdirname, mirdir, curdir, perms ):
    """
    Create the given directory name.  If -M is given in the command line
    options, then a mirror directory is created and 'testdirname' will be
    created as a soft link pointing to the mirror directory.
    """
    assert os.path.isabs( testdirname )

    if mirdir and make_mirror_directory( testdirname, mirdir, curdir, perms ):
        pass

    else:
        if os.path.exists( testdirname ):
            if not os.path.isdir( testdirname ):
                # replace regular file with a directory
                os.remove( testdirname )
                os.mkdir( testdirname )
        else:
            if os.path.islink( testdirname ):
                os.remove( testdirname )  # remove broken softlink
            make_directory( testdirname, perms )

        perms.apply( testdirname )


def make_mirror_directory( testdirname, mirdir, curdir, perms,
                           scratchdirs=SCRATCH_DIR_SEARCH_LIST ):
    """
    Create a directory in another location then soft link 'testdirname' to it.
    Returns False only if 'mirdir' is the word "any" and a suitable scratch
    directory could not be found.
    """
    if platform.uname()[0].lower().startswith('win'):
        raise FatalError( 'test results mirroring is not available on Windows')

    assert os.path.isabs( testdirname )

    if mirdir == 'any':
        mirdir = make_any_scratch_directory( scratchdirs, perms )
        if not mirdir:
            return False

    elif not os.path.isabs( mirdir ):
        mirdir = pjoin( curdir, mirdir )

    assert os.path.isabs( mirdir )

    if not os.path.exists( mirdir ) or not writable_directory( mirdir ):
        raise FatalError( "invalid or non-existent mirror directory: "+mirdir )

    if os.path.samefile( mirdir, curdir ):
        raise FatalError( "mirror directory and current working directory " + \
                "cannot be the same: "+mirdir+' == '+curdir )

    mirdir = pjoin( mirdir, basename( testdirname ) )

    make_leaf_directory( mirdir )
    perms.apply( mirdir )

    force_link_directory( testdirname, mirdir, perms )

    return True


def force_link_directory( linkpath, targetpath, perms ):
    ""
    if os.path.islink( linkpath ):
        path = os.readlink( linkpath )
        if path != targetpath:
            os.remove( linkpath )
            os.symlink( targetpath, linkpath )

    else:
        if os.path.exists( linkpath ):
            if os.path.isdir( linkpath ):
                shutil.rmtree( linkpath )
            else:
                os.remove( linkpath )

        parent = dirname( linkpath )
        make_directory( parent, perms )
        os.symlink( targetpath, linkpath )


def make_leaf_directory( mirdir ):
    ""
    if os.path.exists( mirdir ):
        if not os.path.isdir( mirdir ):
            # replace regular file with a directory
            os.remove( mirdir )
            os.mkdir( mirdir )
    else:
        if os.path.islink( mirdir ):
            os.remove( mirdir )  # remove broken softlink
        os.mkdir( mirdir )


def make_directory( dirpath, perms ):
    ""
    dirpath = normpath( dirpath )

    if dirpath and dirpath != '.':

        subdirs = []
        path = dirpath
        while not os.path.exists(path):

            if basename(path) == '..':
                break

            subdirs.append( path )

            d = dirname( path )
            if not d or d == '.':
                break
            path = d

        while len(subdirs) > 0:
            path = subdirs.pop()

            if os.path.islink( path ):
                os.remove( path )  # remove broken softlink

            os.mkdir( path )
            perms.set( path )


def make_any_scratch_directory( searchdirs, perms ):
    ""
    mirdir = search_and_make_scratch_directory( searchdirs, perms )

    if not mirdir:
        return None  # a scratch dir could not be found

    mirdir = pjoin( mirdir, 'vvtest_rundir' )

    if not os.path.exists( mirdir ):
        os.mkdir( mirdir )

    return mirdir


def search_and_make_scratch_directory( searchdirs, perms ):
    ""
    for d in searchdirs:

        sdir = make_scratch_mirror( d, perms )
        if sdir:
            return sdir

    return None


def make_scratch_mirror( scratch, perms ):
    ""
    if os.path.exists( scratch ) and os.path.isdir( scratch ):

        usr = getUserName()
        ud = pjoin( scratch, usr )

        if os.path.exists(ud):
            if writable_directory(ud):
                return ud

        elif writable_directory( scratch ):
            try:
                os.mkdir(ud)
            except Exception:
                pass
            else:
                perms.apply( ud )
                return ud

    return None


def writable_directory( path ):
    ""
    return os.path.isdir( path ) and \
           os.access( path, os.X_OK ) and \
           os.access( path, os.W_OK )


def getUserName():
    """
    Retrieves the user name associated with this process.
    """
    usr = None
    try:
        import getpass
        usr = getpass.getuser()
    except Exception:
        usr = None

    if usr == None:
        try:
            uid = os.getuid()
            import pwd
            usr = pwd.getpwuid( uid )[0]
        except Exception:
            usr = None

    if usr == None:
        try:
            p = os.path.expanduser( '~' )
            if p != '~':
                usr = basename( p )
        except Exception:
            usr = None

    if usr == None:
        # try manually checking the environment
        for n in ['USER', 'LOGNAME', 'LNAME', 'USERNAME']:
            if os.environ.get(n,'').strip():
                usr = os.environ[n]
                break

    if usr == None:
        raise Exception( "could not determine this process's user name" )

    return usr
