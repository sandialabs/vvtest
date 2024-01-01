#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys
from os.path import dirname, join as pjoin, basename
import time
import json
import platform
import glob
import math

try:
    from shlex import quote
except Exception:
    from pipes import quote

from . import logger
from . import outpututils
from . import pathid


class ListWriter:
    """
    Writes test results to a file format consisting of a file header followed
    by a list of tests.  To support multiple test tree roots, a pathid is
    computed and stored with each test.

    The writer is engaged with command line option --save-results and the
    directory to save results is determined by

        1) --save-results=<path>       : a command line path takes precedence
        2) VVTEST_RESULTS_DIR          : environment variable
        3) vvtest_plugin.py
               def results_directory() : a project plugin function

    The filename contains the vvtest run start date (or --results-date value)
    and may be appended with optional tag given with --results-tag <string>.
    """

    def __init__(self, testlist, loc, permsetter):
        ""
        self.tlist = testlist
        self.loc = loc
        self.permsetter = permsetter

    def initialize(self, rtinfo,
                         destination,
                         datestamp=None,
                         name_tag=None ):
        ""
        self.rtinfo = rtinfo
        self.outdir = destination
        self.datestamp = datestamp
        self.ftag = name_tag

    def postrun(self):
        ""
        self.writeList( finished=True )

    def info(self):
        ""
        self.writeList()

    def writeList(self, finished=False):
        ""
        resdate = self.tlist.getResultsDate()
        if resdate is None:
            resdate = time.time()

        datestr = outpututils.make_date_stamp( resdate, self.datestamp )

        fname = make_filename( self.rtinfo, datestr, self.ftag )

        self._write_results_to_file( finished, self.outdir, fname )

    def _write_results_to_file(self, finished, todir, fname):
        ""
        if not os.path.isdir( todir ):
            os.mkdir( todir )
            self.permsetter.apply(todir)

        tofile = os.path.join( todir, fname )
        pidr = pathid.TestPathIdentification()

        try:
            logger.info( "Writing test results to", tofile )

            hdr = make_header_info( self.rtinfo, self.tlist, finished )

            with open( tofile, 'wt' ) as fp:
                fp.write( json.dumps(hdr)+'\n' )
                tests = list( self.tlist.getTestMap().items() )
                tests.sort()
                for tid,tcase in tests:
                    testdict = get_test_info( pidr, tcase )
                    fp.write( json.dumps(testdict)+'\n' )

        finally:
            self.permsetter.apply( tofile )


def make_filename( rtinfo, datestr, ftag ):
    """
    Requires 'platform' to be defined in the rtinfo dict and optionally
    'compiler' (a string) and 'onopts' (a list of strings).  The format is

        vvtestresults.<datestr>.<platform>.<compiler>.<options>-<ftag>

    but compiler, options, and ftag may not be included.  If given, the
    onopts are alphabetically ordered.
    """
    L = [ 'vvtresults', datestr, rtinfo['platform'] ]
    L.extend( make_option_list(rtinfo) )
    fn = '.'.join(L)

    if ftag:
        fn += '-'+ftag

    return fn


def glob_results_files( resultsdir, rtinfo ):
    """
    Returns a list of all vvtresults files in 'resultsdir' directory matching
    the given 'rtinfo' platform and options with any date or ftag.
    """
    pat = '.'.join( [rtinfo['platform'],]+make_option_list(rtinfo) )

    fnL = []
    for bn in os.listdir(resultsdir):
        L1 = bn.split('.',2)
        if len(L1) == 3 and L1[0] == 'vvtresults':
            L2 = L1[2].split('-',1)
            if L2[0] == pat:
                fnL.append( pjoin(resultsdir,bn) )

    return fnL


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
        "onopts"       : ','.join( sorted(rti.get("onopts",[])) ),
        "offopts"      : ','.join( sorted(rti.get("offopts",[])) ),
        'rundir'       : rti['rundir'],
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

    hdr['num_skip'] = 0
    hdr['num_notrun'] = 0
    hdr['num_running'] = 0
    hdr['num_runskip'] = 0
    hdr['num_pass'] = 0
    hdr['num_fail'] = 0
    hdr['num_diff'] = 0
    hdr['num_timeout'] = 0
    for tcase in tlist.getTests():
        res = outpututils.get_test_result_string( tcase.getStat() )
        hdr['num_'+res] += 1

    return hdr


def get_test_info( pidr, tcase ):
    ""
    spec = tcase.getSpec()
    stat = tcase.getStat()

    res = outpututils.get_test_result_string( stat )

    pathid = pidr.get_path_id( spec.getFilename() )
    testid = list( spec.getID() )
    testid[0] = pathid if pathid else spec.getFilepath()

    D = { 'testid': tuple(testid),
          'result': res, }

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
            if line.strip() and not line.strip().startswith('#'):
                i += 1
                if i == 1:
                    fileinfo = json.loads( line.strip() )
                else:
                    D = json.loads( line.strip() )
                    testinfo.append( D )

    return fileinfo,testinfo


def update_results_files( reftime, resultsdir, specs, rtinfo, ftag ):
    """
    The 'reftime' should be time.time() when vvtest started running.

    Currently, 'specs' can only be a number, which is the number of days of
    files to keep.  The specifications could be extended as demand requires.
    """
    try:
        v = float( specs.strip() )
        assert not v < 0.0, 'SPECS num days cannot be negative'
        numdays = int( v*1000000.0 + 0.5 ) / 1000000.0
        minfiles = int(math.ceil(numdays))

        datestr = outpututils.make_date_stamp( reftime-numdays*24*60*60, None )
        cutoff_fn = make_filename( rtinfo, datestr, ftag )

        fnL = list_candidate_files( resultsdir, rtinfo, ftag )

        idx = find_cutoff_index( fnL, cutoff_fn )
        if idx < minfiles:
            # keep at least this many files, no matter how old
            idx = minfiles

        delete_files( fnL[idx:] )

    except Exception:
        xs,tb = outpututils.capture_traceback( sys.exc_info() )
        logger.warn( '\n'+tb+'\n\n*** error updating results directory: ' + \
                     repr(resultsdir) )


def list_candidate_files( resultsdir, rtinfo, ftag ):
    ""
    fnL = []
    for fn in glob_results_files( resultsdir, rtinfo ):
        if ftag:
            if fn.endswith('-'+ftag):
                fnL.append(fn)
        else:
            if '-' not in fn.split('.',2)[2].split( rtinfo['platform'], 1 )[1]:
                fnL.append(fn)

    fnL.sort()
    fnL.reverse()  # most recent first
    return fnL


def find_cutoff_index( fnL, cutoff_fn ):
    ""
    for i,fn in enumerate(fnL):
        bn = basename(fn)
        if cutoff_fn > bn:
            return i
    return len(fnL)


def delete_files( filenames ):
    ""
    for fn in filenames:
        logger.info( 'Deleting file '+repr(fn) )
        os.remove(fn)
