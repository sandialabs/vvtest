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

    def __init__(self, loc, permsetter):
        ""
        self.loc = loc
        self.permsetter = permsetter

    def initialize(self, rtinfo,
                         destination,
                         datestamp=None,
                         name_tag=None,
                         scpexe='scp' ):
        ""
        self.rtinfo = rtinfo
        self.outdir = destination
        self.datestamp = datestamp
        self.ftag = name_tag
        self.scpexe = scpexe

    def prerun(self, atestlist, verbosity):
        ""
        self.writeList( atestlist, inprogress=True )

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

        fname = self.makeFilename( datestr )

        self._write_results_to_file( atestlist, inprogress, self.outdir, fname )

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
        onopts = self.rtinfo.get( 'onopts' )

        if cplr:
            opL = [ cplr ]
        else:
            opL = []

        for op in onopts:
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

        tr.writeResults( filename, pname, cplr, mach, self.rtinfo['rundir'], inprogress )
