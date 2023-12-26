#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys
from os.path import dirname, join as pjoin, basename
import time
import json
import platform

try:
    from shlex import quote
except Exception:
    from pipes import quote

from . import logger
from . import outpututils
from . import pathid


# the test root marker filename
VVTEST_ROOT_FILENAME = '.vvtest.root'


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
        self.writeList( atestlist )

    def postrun(self, atestlist):
        ""
        self.writeList( atestlist, finished=True )

    def info(self, atestlist):
        ""
        self.writeList( atestlist )

    def writeList(self, atestlist, finished=False):
        ""
        resdate = atestlist.getResultsDate()
        if resdate is None:
            resdate = time.time()

        datestr = outpututils.make_date_stamp( resdate, self.datestamp )

        fname = make_filename( self.rtinfo, datestr, self.ftag )

        self._write_results_to_file( atestlist, finished, self.outdir, fname )

    def _write_results_to_file(self, atestlist, finished, todir, fname):
        ""
        if not os.path.isdir( todir ):
            os.mkdir( todir )
            self.permsetter.apply(todir)

        tofile = os.path.join( todir, fname )

        try:
            logger.info( "Writing test results to", tofile )

            hdr = make_header_info( self.rtinfo, atestlist, finished )

            with open( tofile, 'wt' ) as fp:
                fp.write( json.dumps(hdr)+'\n' )
                tests = list( atestlist.getTestMap().items() )
                tests.sort()
                for tid,tcase in tests:
                    # magic: need to move pathid object into this function
                    testdict = get_test_info( tcase )
                    fp.write( json.dumps(testdict)+'\n' )

        finally:
            self.permsetter.apply( tofile )


def make_filename( rti, datestr, ftag ):
    ""
    L = [ 'vvtresults', datestr, rti['platform'] ]
    L.extend( make_option_list(rti) )

    if ftag:
        L.append( ftag )

    return '.'.join( L )


def make_filename_glob_pattern( rti ):
    ""
    L = [ 'vvtresults', '*', rti['platform'] ]
    L.extend( make_option_list(rti) )
    return '.'.join(L)+'*'


def make_option_list( rti ):
    ""
    cplr = rti.get( 'compiler', None )
    if cplr:
        opL = []
        for op in rti.get('onopts',[]):
            if op != cplr:
                opL.append( op )
        return [cplr]+sorted(opL)
    else:
        return sorted( rti.get('onopts',[] ) )


def make_header_info( rti, tlist, finished ):
    ""
    t0 = tlist.getResultsDate()
    t1 = tlist.getFinishDate()
    xcode = tlist.getFinishCode()
    if finished and t1 is None and xcode is None:
        t1 = time.time()
        xcode = 0

    hdr = {
        "command"      : ' '.join(quote(s) for s in rti.get("cmdline", [])),
        'platform'     : rti.get('platform',None),
        "onopts"       : ','.join( rti.get("onopts",[]) ),
        "offopts"      : ','.join( rti.get("offopts",[]) ),
        'python'       : sys.executable,
        'sys.platform' : sys.platform,
        'hostname'     : platform.uname()[1],
        'starttime'    : t0,
        'endtime'      : t1,
        'returncode'   : xcode,
    }

    cplr = rti.get('compiler',None)
    if cplr:
        hdr['compiler'] = cplr
    if t0:
        hdr['startdate'] = time.ctime(t0)
    if t1:
        hdr['enddate'] = time.ctime(t1)
    if t0 and t1:
        hdr['duration'] = t1-t0

    # magic: include num tests pass, fail, skip, etc

    return hdr


def get_test_info( tcase ):
    ""
    pidr = pathid.TestPathIdentification()

    spec = tcase.getSpec()
    stat = tcase.getStat()

    res = stat.getResultStatus()

    D = {
        'testid':spec.getID(),
        'pathid': pidr.get_path_id( spec.getFilename() ),
        'result': res,
    }

    if 'TDD' in spec.getKeywords():
        D['TDD'] = True

    if stat.skipTest():
        D['skip'] = stat.getReasonForSkipTest()

    tm = stat.getTimeoutValue( None )
    if tm is not None:
        D['timeout'] = tm

    tm = stat.getRuntime( None )
    if tm is not None:
        D['runtime'] = tm

    tm = stat.getStartDate( None )
    if tm is not None:
        D['startdate'] = tm

    return D


def read_results_file( fname ):
    ""
    fileinfo = None
    testinfo = []

    i = 0
    with open( fname, 'rt' ) as fp:
        for line in fp:
            if not line.strip().startswith('#'):
                i += 1
                if i == 1:
                    fileinfo = json.loads( line.strip() )
                else:
                    D = json.loads( line.strip() )
                    testinfo.append( D )

    return fileinfo,testinfo
