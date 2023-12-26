#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys
import time

from . import logger
from . import outpututils


class ConsoleWriter:

    def __init__(self):
        ""
        pass

    def initialize(self, rtinfo, verbose=0, sortspec=None, maxnonpass=32):
        ""
        self.rtinfo = rtinfo
        self.verbose = verbose
        self.sortspec = sortspec
        self.maxnonpass = maxnonpass

    def prerun(self, atestlist, verbosity):
        ""
        level = get_prerun_list_level( verbosity, self.verbose )

        self._write_test_list_results( atestlist, level )
        self._write_summary( atestlist, 'Test list:' )

    def postrun(self, atestlist):
        ""
        if atestlist.numActive() > 0:
            level = 1 + self.verbose
            self._write_test_list_results( atestlist, level )
            self._write_summary( atestlist, 'Summary:' )

        logger.info( make_finish_info_string( self.rtinfo, atestlist ) )

    def info(self, atestlist):
        ""
        level = 1 + self.verbose
        self._write_test_list_results( atestlist, level )
        self._write_summary( atestlist, 'Summary:' )

    def timings(self, atestlist):
        ""
        cwd = os.getcwd()

        tosum,tL = collect_timing_list( atestlist, self.rtinfo['rundir'], cwd )

        fmt = '%8s %8s %s'
        logger.info( fmt % ('TIMEOUT','RUNTIME','TEST') )
        for to,rt,ds in tL:
            logger.info( fmt % (to, rt, ds) )

        logger.info( 'TIMEOUT SUM =', outpututils.colon_separated_time(tosum) )

    def _write_summary(self, atestlist, label):
        ""
        logger.info( label )

        tcaseL = atestlist.getTests()
        parts = outpututils.partition_tests_by_result( tcaseL )

        n = len( parts['pass'] ) + \
            len( parts['diff'] ) + \
            len( parts['fail'] ) + \
            len( parts['timeout'] )
        self.iwrite( 'completed:', n )
        if n > 0:
            self._write_part_count( parts, 'pass' )
            self._write_part_count( parts, 'diff' )
            self._write_part_count( parts, 'fail' )
            self._write_part_count( parts, 'timeout' )

        self._write_part_count( parts, 'notdone', indent=False )
        self._write_part_count( parts, 'notrun', indent=False )

        self._write_part_count( parts, 'skip', indent=False, label='skipped' )
        self._write_skips( parts['skip'] )

        self.iwrite( 'total:', len(tcaseL) )

    def _write_skips(self, skiplist):
        ""
        skipmap = self._collect_skips( skiplist )

        keys = list( skipmap.keys() )
        keys.sort()
        for k in keys:
            self.iwrite( ' %6d' % skipmap[k], 'due to "'+k+'"' )

    def _collect_skips(self, skiplist):
        ""
        skipmap = {}

        for tcase in skiplist:
            reason = tcase.getStat().getReasonForSkipTest()
            if reason not in skipmap:
                skipmap[reason] = 0
            skipmap[reason] += 1

        return skipmap

    def _write_part_count(self, parts, part_name, indent=True, label=None):
        ""
        n = len( parts[part_name] )

        if label == None:
            label = part_name

        if n > 0:
            if indent:
                self.iwrite( ' %6d'%n, label  )
            else:
                self.iwrite( label+':', n  )

    def _write_test_list_results(self, atestlist, level):
        """
            level = 0 : no list
                    1 : only non-pass and with truncate
                    2 : active
                    3 : all (include skips)
        """
        cwd = os.getcwd()

        if level <= 2:
            tcaseL = atestlist.getActiveTests( self.sortspec )
        else:
            tcaseL = atestlist.getTests()

        if len( tcaseL ) > 0:
            logger.info( "==================================================" )

        numwritten = 0

        if level == 1:
            numwritten = self._write_nonpass_notdone( tcaseL, cwd )

        elif level >= 2:
            for tcase in tcaseL:
                self.writeTest( tcase, cwd )
            numwritten = len( tcaseL )

        if numwritten > 0:
            logger.info( "==================================================" )

    def _adjust_detail_level_by_verbose(self, level):
        ""
        if self.verbose > 1:
            level += 1
        if self.verbose > 2:
            level += 1

        return level

    def _write_nonpass_notdone(self, tcaseL, cwd):
        ""
        numwritten = 0
        numnonpass = 0
        for tcase in tcaseL:

            if self._nonpass_or_notdone( tcase ):
                if numwritten < self.maxnonpass:
                    self.writeTest( tcase, cwd )
                    numwritten += 1
                numnonpass += 1

        if numwritten < numnonpass:
            logger.info( '... non-pass list too long'
                         ' (add -v for full list or run again with -iv)' )

        return numwritten

    def _nonpass_or_notdone(self, tcase):
        ""
        if tcase.getStat().isDone() and \
                not tcase.getStat().passed():
            return True

        if tcase.getStat().isNotDone():
            return True

        return False

    def iwrite(self, *args):
        ""
        logger.info( '   ', *args )

    def writeTest(self, tcase, cwd):
        ""
        astr = outpututils.XstatusString( tcase, self.rtinfo['rundir'], cwd )
        logger.info( astr )


def make_finish_info_string( rtinfo, tlist ):
    ""
    s = '\n'

    fin = tlist.getFinishDate()
    if fin is not None:
        s += 'Finish date: '+time.ctime( fin )

        start = tlist.getResultsDate()
        if start is not None:
            dt = fin - start
            elapsed = outpututils.pretty_time( dt )
            s += ' (elapsed time '+elapsed+')'

    else:
        s += 'Finish date: '+time.ctime()

    return s


def get_prerun_list_level( verbosity, verbose ):
    ""
    if verbose < 2:
        level = verbosity + verbose
        if level == 1:
            # skip level=1 for prerun (only listing non-pass has no value)
            level += 1
    else:
        # align with postrun -vv
        level = verbose + 1

    return level


def collect_timing_list( tlist, test_dir, cwd ):
    ""
    tL = []

    for tcase in tlist.getTests():
        tspec = tcase.getSpec()
        tstat = tcase.getStat()

        ds = tspec.getDisplayString()
        lds = outpututils.location_display_string( tspec, test_dir, cwd )
        rt = tstat.getRuntime( -1 )
        to = tstat.getAttr( 'timeout', -1 )

        tL.append( ( to, rt, ds, lds ) )

    tL.sort()

    tosum = 0
    sortL = []
    for to,rt,ds,lds in tL:

        if rt < 0:
            s_rt = ''
        else:
            s_rt = outpututils.colon_separated_time(rt)

        if to < 0:
            s_to = 'None'
        else:
            tosum += to
            s_to = outpututils.colon_separated_time(to)

        sortL.append( (s_to,s_rt,lds) )

    return tosum,sortL
