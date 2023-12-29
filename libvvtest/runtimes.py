#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys
from os.path import join as pjoin, basename, dirname
import time
import glob

from . import listwriter
from . import pathid
from . import logger
from .outpututils import capture_traceback

# only this number of previous results files will be read when searching
# for a test runtime
NUM_HISTORICAL_RESULTS_FILES = 7


class RuntimesLookup:

    def __init__(self, rtinfo, resultsdir):
        ""
        self.rtinfo = rtinfo
        self.resultsdir = resultsdir

        self.pathcache = pathid.TestPathIdentification()
        self.filecache = []  # list of pairs (filename, test key -> results dict)

    def load(self):
        ""
        if self.resultsdir is not None:
            if check_results_directory( self.resultsdir ):

                fnL = find_results_files( self.rtinfo, self.resultsdir,
                                          NUM_HISTORICAL_RESULTS_FILES )
                for fn in fnL:
                    self.filecache.append( [fn,None] )

                # read in the first file; the rest are only read in as needed
                if len(fnL) > 0:
                    get_results_file_map( self.filecache, 0 )

    def getRunTime(self, testspec):
        """
        Search for a runtime for the given test from results files saved from
        previous vvtest runs.
        """
        rt = res = None

        if self.filecache:
            pathid = self.pathcache.get_path_id( testspec.getFilename() )
            if pathid:
                tkey = make_test_key( pathid, testspec.getID() )
                rt,res = find_runtime_for_test( tkey, self.filecache )

        return rt,res


def find_runtime_for_test( testkey, fcache ):
    """
    Find the most recent test with a valid runtime.  A more sophisticated
    algorithm could be performed, such as

        - accept a timeout runtime only if a timeout occurs two times in a row
        - take the max runtime over some period of time (7 days?)
    """
    for i in range(len(fcache)):
        tmap = get_results_file_map( fcache, i )
        if tmap:
            tinfo = tmap.get( testkey, None )
            if tinfo:
                return tinfo['runtime'],tinfo['result']

    return None, None


def get_results_file_map( fcache, index ):
    ""
    L = fcache[index]
    if L[1] is None:
        tmap = {}
        try:
            read_results_file_into_map( L[0], tmap )
        except Exception:
            xs,tb = capture_traceback( sys.exc_info() )
            logger.warn( '\n'+tb+'\n\n*** error reading results file: ' + \
                         repr(L[0])+'\n...ignoring...' )
        L[1] = tmap

    return L[1]


def read_results_file_into_map( filename, tmap ):
    """
    Reads the results file and adds each test that pass, diff, or timeout
    into the given map, where the key is obtained from make_test_key().
    """
    finfo,tinfo = listwriter.read_results_file( filename )

    for tD in tinfo:
        testkey = make_test_key( tD['pathid'], tD['testid'] )
        if testkey:
            res = tD.get('result',None)
            if res == 'pass' or res == 'diff' or res == 'timeout':
                if tD.get('runtime',None) is not None:
                    tmap[ testkey ] = tD


def make_test_key( pathid, testid ):
    ""
    if pathid:
        L = [ pathid ]
        L.extend( testid[1:] )
        return tuple(L)

    return None


def check_results_directory( resultsdir ):
    ""
    if resultsdir and os.path.isdir(resultsdir):
        if os.access( resultsdir, os.R_OK|os.X_OK ):
            return True
        else:
            logger.warn( 'Could not read vvtest results directory: '+repr(resultsdir) )
    else:
        logger.warn( 'Invalid vvtest results directory: '+repr(resultsdir) )

    return False


def find_results_files( rtinfo, resultsdir, maxfiles=7 ):
    """
    returns a list of filenames ordered most recent first
    """
    fnL = []

    try:
        fpat = listwriter.make_filename_glob_pattern( rtinfo )
        fnL = glob.glob( pjoin( resultsdir, fpat ) )
        fnL.sort()
        fnL.reverse()
        fnL = fnL[:maxfiles]

    except Exception:
        xs,tb = capture_traceback( sys.exc_info() )
        logger.warn( '\n'+tb+'\n\n*** error collecting results files from ' + \
                     repr(resultsdir)+'\n...ignoring...' )

    return fnL
