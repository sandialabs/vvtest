#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys
import time

from . import outpututils


class ConsoleWriter:

    def __init__(self, statushandler, output_file_obj, results_test_dir):
        ""
        self.statushandler = statushandler
        self.fileobj = output_file_obj
        self.testdir = results_test_dir

        self.sortspec = None

    def setSortingSpecification(self, sortspec):
        ""
        self.sortspec = sortspec

    def writeTestList(self, atestlist, abbreviate=False):
        ""

        if abbreviate:
            self._write_summary( atestlist )
        else:
            self._write_full_list( atestlist )

    def _write_summary(self, atestlist):
        ""
        testL = atestlist.getTests()
        parts = outpututils.partition_tests_by_result( self.statushandler, testL )

        n = len( parts['pass'] ) + len( parts['diff'] ) + len( parts['timeout'] )
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

        for tst in skiplist:
            reason = self.statushandler.getReasonForSkipTest( tst )
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

    def _write_full_list(self, atestlist):
        ""
        cwd = os.getcwd()

        self.write( "==================================================" )

        testL = atestlist.getActiveTests( self.sortspec )

        for atest in testL:
            self.writeTest( atest, cwd )

        self.write( "==================================================" )

        parts = outpututils.partition_tests_by_result( self.statushandler, testL )
        self.write( "Summary:", outpututils.results_summary_string( parts ) )

    def write(self, *args):
        ""
        self.fileobj.write( ' '.join( [ str(arg) for arg in args ] ) + '\n' )
        self.fileobj.flush()

    def iwrite(self, *args):
        ""
        argstr = ' '.join( [ str(arg) for arg in args ] )
        self.write( '   ', *args )

    def writeTest(self, atest, cwd):
        ""
        astr = outpututils.XstatusString( self.statushandler, atest,
                                          self.testdir, cwd )
        self.write( astr )
