#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys
from os.path import join as pjoin

from .errors import FatalError, TestSpecError
from .staging import tests_are_related_by_staging
from .pathutil import change_directory


class TestFileScanner:

    def __init__(self, loc, creator, tcasefactory,
                       path_list=[],
                       specform=None,
                       warning_output_stream=sys.stdout):
        """
        The 'loc' is a Locator object.
        If 'specform' is not None, it must be a list of strings, such as
        'vvt' and 'xml'.  The scanner will only pick up files for those test
        specification forms.  Default is only 'vvt' files.
        """
        self.loc = loc
        self.creator = creator
        self.fact = tcasefactory
        self.path_list = path_list
        self.warnout = warning_output_stream

        self.extensions = creator.getValidFileExtensions( specform )

        self.xdirmap = {}  # TestSpec xdir -> TestCase object

    def scanPaths(self, testlist):
        ""
        for d in self.path_list:
            if not os.path.exists(d):
                raise FatalError( 'scan path does not exist: ' + str(d) )

            self.scanPath( testlist, d )

    def scanPath(self, testlist, path):
        """
        Recursively scans for test XML or VVT files starting at 'path'.
        """
        if os.path.isfile( path ):
            basedir,fname = os.path.split( path )
            self.readTestFile( testlist, basedir, fname )

        else:
            for root,dirs,files in os.walk( path ):
                self._scan_recurse( testlist, path, root, dirs, files )

    def completeTestParsing(self, testlist):
        ""
        with change_directory( self.loc.make_abspath('.') ):
            for tcase in testlist.getActiveTests():
                tspec = tcase.getSpec()
                if not tspec.constructionCompleted():
                    self.creator.reparse( tspec )

    def _scan_recurse(self, testlist, basedir, d, dirs, files):
        """
        This function is given to os.walk to recursively scan a directory
        tree for test XML files.  The 'basedir' is the directory originally
        sent to the os.walk function.
        """
        d = os.path.normpath(d)

        reldir = os.path.relpath( d, basedir )

        # scan files with extension specific extensions; soft links to
        # directories are skipped by os.walk so special handling is performed

        for f in files:
            bn,ext = os.path.splitext(f)
            if bn and ext in self.extensions:
                fname = os.path.join(reldir,f)
                self.readTestFile( testlist, basedir, fname )

        linkdirs = []
        for subd in list(dirs):
            rd = os.path.join( d, subd )
            if not os.path.exists(rd) or \
                    subd.startswith("TestResults.") or \
                    subd.startswith("Build_") or \
                    is_vvtest_cache_directory(rd):
                # Note: using specific directory names to exclude is not
                # necessary anymore (because of the vvtest.cache file), but
                # is benign (until its not :)
                dirs.remove( subd )
            elif os.path.islink(rd):
                linkdirs.append( rd )

        # TODO: should check that the soft linked directories do not
        #       point to a parent directory of any of the directories
        #       visited thus far (to avoid an infinite scan loop)
        #       - would have to use os.path.realpath() or something because
        #         the actual path may be the softlinked path rather than the
        #         path obtained by following '..' all the way to root

        # manually recurse into soft linked directories
        for ld in linkdirs:
            for lroot,ldirs,lfiles in os.walk( ld ):
                self._scan_recurse( testlist, basedir, lroot, ldirs, lfiles )

    def readTestFile(self, testlist, basepath, relfile):
        """
        Initiates the parsing of a test file.  XML test descriptions may be
        skipped if they don't appear to be a test file.  Attributes from
        existing tests will be absorbed.
        """
        # assert basepath and os.path.isabs( basepath )
        assert relfile and not os.path.isabs( relfile )

        basepath = os.path.normpath( basepath or '.' )
        relfile  = os.path.normpath( relfile )

        assert relfile

        try:
            testL = self.creator.fromFile( relfile, basepath )
        except TestSpecError:
            print_warning( self.warnout,
                           "skipping file", os.path.join( basepath, relfile ),
                           "because", str( sys.exc_info()[1] ) )
            testL = []

        for tspec in testL:
            if not self._is_duplicate_execute_directory( tspec ):
                tcase = self.fact.new( tspec )
                if tspec.hasKeyword( 'TDD' ):
                    tcase.getStat().setAttr( 'TDD', True )
                testlist.addTest( tcase )
                self.xdirmap[ tspec.getExecuteDirectory() ] = tcase

    def _is_duplicate_execute_directory(self, tspec):
        ""
        xdir = tspec.getExecuteDirectory()

        tcase0 = self.xdirmap.get( xdir, None )

        if tcase0 != None and \
           not tests_are_related_by_staging( tcase0.getSpec(), tspec ):

            tspec0 = tcase0.getSpec()

            warn = [ 'ignoring test with duplicate execution directory',
                     '      first   : ' + tspec0.getFilename(),
                     '      second  : ' + tspec.getFilename(),
                     '      exec dir: ' + xdir,
                     '      stringid: ' + tspec.getDisplayString() ]

            ddir = tspec.getDisplayString()
            if ddir != xdir:
                warn.append( '       test id : ' + ddir )

            print_warning( self.warnout, '\n'.join( warn ) )

            return True

        return False


def is_vvtest_cache_directory( cdir ):
    ""
    fname = pjoin( cdir, 'vvtest.cache' )
    if os.path.exists( fname ):
        return True

    # June 2022: name changed from test.cache to vvtest.cache, but look
    #            for the old name for a while (a year?)
    # this note is also in vvtest and location.py
    fname = pjoin( cdir, 'test.cache' )
    if os.path.exists( fname ):
        with open( fname, 'rt' ) as fp:
            ver = fp.read(20).strip()
        if ver.startswith('VERSION='):
            return True

    return False


def print_warning( stream, *args ):
    ""
    stream.write( '*** warning: ' )
    stream.write( ' '.join( [ str(arg) for arg in args ] ) + '\n' )
    stream.flush()
