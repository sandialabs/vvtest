#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys
import time
from os.path import join as pjoin

from . import outpututils


class HTMLWriter:

    def __init__(self, permsetter, output_filename, results_test_dir):
        ""
        self.permsetter = permsetter
        self.filename = os.path.normpath( os.path.abspath( output_filename ) )
        self.testdir = results_test_dir

    def setInfoObjects(self, rtinfo):
        ""
        self.rtinfo = rtinfo

    def prerun(self, atestlist, verbosity):
        ""
        pass

    def midrun(self, atestlist):
        ""
        pass

    def postrun(self, atestlist):
        ""
        self.writeDocument( atestlist )

    def info(self, atestlist):
        ""
        self.writeDocument( atestlist )

    def writeDocument(self, tlist):
        """
        Opens and writes an HTML summary file in the test directory.
        """
        datestamp = self.rtinfo.getInfo( 'startepoch', time.time() )
        datestr = outpututils.make_date_stamp( datestamp, None,
                                               "%Y-%m-%d %H:%M:%S" )

        tcaseL = tlist.getActiveTests()

        parts = outpututils.partition_tests_by_result( tcaseL )

        sumstr = outpututils.results_summary_string( parts )

        fp = open( self.filename, "w" )
        try:
            fp.write( "<html>\n<head>\n<title>Test Results</title>\n" )
            fp.write( "</head>\n<body>\n" )

            # a summary section

            fp.write( "<h1>Summary</h1>\n" )
            fp.write( "  <ul>\n" )
            fp.write( "  <li> Test date: " + datestr + " </li>\n" )
            fp.write( "  <li> Directory: " + self.testdir + " </li>\n" )
            fp.write( "  <li> " + sumstr + "</li>\n" )
            fp.write( "  </ul>\n" )

            # segregate the tests into implicit keywords, such as fail and diff

            fp.write( '<h1>Tests that showed "fail"</h1>\n' )
            self.writeTestList( fp, parts['fail'] )
            fp.write( '<h1>Tests that showed "timeout"</h1>\n' )
            self.writeTestList( fp, parts['timeout'] )
            fp.write( '<h1>Tests that showed "diff"</h1>\n' )
            self.writeTestList( fp, parts['diff'] )
            fp.write( '<h1>Tests that showed "notdone"</h1>\n' )
            self.writeTestList( fp, parts['notdone'] )
            fp.write( '<h1>Tests that showed "pass"</h1>\n' )
            self.writeTestList( fp, parts['pass'] )
            fp.write( '<h1>Tests that showed "notrun"</h1>\n' )
            self.writeTestList( fp, parts['notrun'] )

            fp.write( "</body>\n</html>\n" )

        finally:
            fp.close()
            self.permsetter.apply( os.path.abspath( self.filename ) )

    def writeTestList(self, fp, tlist):
        """
        Used by printHTMLResults().  Writes the HTML for a list of tests to the
        HTML summary file.
        """
        cwd = os.getcwd()

        fp.write( '  <ul>\n' )

        for tcase in tlist:

            xs = outpututils.XstatusString( tcase, self.testdir, cwd )
            fp.write( '  <li><code>' + xs + '</code>\n' )

            tspec = tcase.getSpec()

            tdir = pjoin( self.testdir, tspec.getExecuteDirectory() )
            assert cwd == tdir[:len(cwd)]
            reltdir = tdir[len(cwd)+1:]

            fp.write( "<ul>\n" )
            thome = tspec.getRootpath()
            xfile = pjoin( thome, tspec.getFilepath() )
            fp.write( '  <li>XML: <a href="file://' + xfile + '" ' + \
                             'type="text/plain">' + xfile + "</a></li>\n" )
            fp.write( '  <li>Parameters:<code>' )
            for (k,v) in tspec.getParameters().items():
                fp.write( ' ' + k + '=' + v )
            fp.write( '</code></li>\n' )
            kwlist = tspec.getKeywords() + tcase.getStat().getResultsKeywords()
            fp.write( '  <li>Keywords: <code>' + ' '.join( kwlist ) + \
                       '</code></li>\n' )
            xs = outpututils.XstatusString( tcase, self.testdir, cwd )
            fp.write( '  <li>Status: <code>' + xs + '</code></li>\n' )
            fp.write( '  <li> Files:' )
            if os.path.exists(reltdir):
                for f in os.listdir(reltdir):
                    fp.write( ' <a href="file:' + pjoin(reltdir,f) + \
                              '" type="text/plain">' + f + '</a>' )
            fp.write( '</li>\n' )
            fp.write( "</ul>\n" )
            fp.write( "</li>\n" )

        fp.write( '  </ul>\n' )
