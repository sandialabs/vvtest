#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys
from os.path import dirname
import time

from . import logger
from . import outpututils
from . import fmtresults


class ListWriter:
    """
    Option is

      --save-results

    which writes to the platform config testing directory (which looks first at
    the TESTING_DIRECTORY env var).  Can add

      --results-tag <string>

    which is appended to the results file name.  A date string is embedded in
    the file name, which is obtained from the date of the first test that
    ran.  But if the option

      --results-date <number or string>

    is given on the vvtest command line, then that date is used instead.
    """

    def __init__(self, loc, permsetter, output_dir, results_test_dir, scpexe='scp'):
        ""
        self.loc = loc
        self.permsetter = permsetter
        self.outdir = output_dir
        self.testdir = results_test_dir
        self.scpexe = scpexe

        self.datestamp = None
        self.onopts = []
        self.ftag = None

    def setOutputDate(self, datestamp):
        ""
        self.datestamp = datestamp

    def setInfoObjects(self, rtinfo):
        ""
        self.rtinfo = rtinfo

    def setNamingTags(self, on_option_list, final_tag):
        ""
        self.onopts = on_option_list
        self.ftag = final_tag

    def prerun(self, atestlist, verbosity):
        ""
        self.writeList( atestlist, inprogress=True )

    def midrun(self, atestlist):
        ""
        pass

    def postrun(self, atestlist):
        ""
        if atestlist.numActive() > 0:
            self.writeList( atestlist )

    def info(self, atestlist):
        ""
        self.writeList( atestlist )

    def writeList(self, atestlist, inprogress=False):
        ""
        datestamp = self.rtinfo.get( 'startepoch', time.time() )
        datestr = outpututils.make_date_stamp( datestamp, self.datestamp )

        if is_target_like_scp( self.outdir ):
            todir = self.testdir
        else:
            todir = self.outdir

        fname = self.makeFilename( datestr )

        self._write_results_to_file( atestlist, inprogress, todir, fname )

        if todir != self.outdir:
            scp_file_to_remote( self.scpexe, todir, fname, self.outdir )

    def _write_results_to_file(self, atestlist, inprogress, todir, fname):
        ""
        if not os.path.isdir( todir ):
            os.mkdir( todir )

        tofile = os.path.join( todir, fname )

        try:
            tcaseL = atestlist.getActiveTests()
            logger.info( "Writing results of", len(tcaseL), "tests to", tofile )
            self.writeTestResults( tcaseL, tofile, inprogress )

        finally:
            self.permsetter.apply( tofile )

    def makeFilename(self, datestr):
        ""
        pname = self.rtinfo.get( 'platform' )
        cplr = self.rtinfo.get( 'compiler' )

        if cplr:
            opL = [ cplr ]
        else:
            opL = []

        for op in self.onopts:
            if op != cplr:
                opL.append( op )
        optag = '+'.join( opL )

        L = [ 'results', datestr, pname, optag ]
        if self.ftag:
            L.append( self.ftag )
        basename = '.'.join( L )

        return basename

    def writeTestResults(self, tcaseL, filename, inprogress):
        ""
        dcache = {}
        tr = fmtresults.TestResults()

        for tcase in tcaseL:
            srcdir = dirname( self.loc.make_abspath( tcase.getSpec().getFilename() ) )
            rootrel = fmtresults.determine_rootrel( srcdir, dcache )
            if rootrel:
                tr.addTest( tcase, rootrel )

        pname = self.rtinfo.get( 'platform' )
        cplr = self.rtinfo.get( 'compiler' )
        mach = os.uname()[1]

        tr.writeResults( filename, pname, cplr, mach, self.testdir, inprogress )


def is_target_like_scp( tdir ):
    ""
    sL = tdir.split( ':', 1 )
    if len(sL) == 2:
        if os.pathsep not in sL[0] and '/' not in sL[0]:
            return True

    return False


def scp_file_to_remote( scpexe, fromdir, fname, destdir ):
    ""
    import subprocess
    import pipes

    fromfile = os.path.join( fromdir, fname )
    tofile = os.path.join( destdir, fname )

    cmd = scpexe + ' -p '+pipes.quote(fromfile)+' '+pipes.quote(tofile)

    logger.info( cmd )
    sys.stdout.flush() ; sys.stderr.flush()

    x = subprocess.call( cmd, shell=True )

    if x != 0:
        sys.stdout.flush() ; sys.stderr.flush()
        logger.warn( '\n*** vvtest warning: scp seems to have failed\n' )
