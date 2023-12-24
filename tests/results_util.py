#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys
import time
import filecmp
import glob
import datetime
import json

import vvtestutils as vtu
import testutils as util

import libvvtest.runtimes as runtimes


def write_tests_cat_dog_circle( in_subdir=None ):
    ""
    cwd = os.getcwd()

    if in_subdir:
        if not os.path.exists( in_subdir ):
            os.mkdir( in_subdir )
            time.sleep(1)

        os.chdir( in_subdir )

    try:
        write_test_cat()
        write_test_dog()
        write_test_circle()

    finally:
        if in_subdir:
            os.chdir( cwd )

def write_test_cat( sleep_time=1 ):
    ""
    util.writefile( "one/cat.vvt", """
        import time
        time.sleep("""+str(sleep_time)+""")
        """ )

def write_test_dog( sleep_time=2 ):
    ""
    util.writefile( "one/dog.vvt", """
        import time
        time.sleep("""+str(sleep_time)+""")
        """ )

def write_test_circle():
    ""
    util.writefile( "two/circle.vvt", """
        import time
        time.sleep(3)
        """ )


def assert_cat_dog_circle_testresults_contents( resultsfname ):
    ""
    fileinfo,testinfo = read_results_file( resultsfname )

    assert len(testinfo) == 3
    assert list( testinfo[0]['testid'] ) == ['one/cat.vvt', 'cat']
    assert testinfo[0]['runtime'] >= 1
    assert list( testinfo[1]['testid'] ) == ['one/dog.vvt', 'dog']
    assert testinfo[1]['runtime'] >= 2
    assert list( testinfo[2]['testid'] ) == ['two/circle.vvt', 'circle']
    assert testinfo[2]['runtime'] >= 3


def create_runtimes_and_results_file( testresults_dir, testsrcdir=None ):
    """
    Save test results from the 'testresults_dir' to the TESTING_DIRECTORY
    and return the results filename.
    """
    vtu.runvvtest( '-i --save-results', chdir=testresults_dir )
    resultsfname = get_latest_results_filename()
    return resultsfname


def assert_results_file_has_tests( filename, *tests, **kwargs ):
    ""
    fileinfo,testinfo = read_results_file( filename )

    for i,tst in enumerate(tests):
        tD = testinfo[i]
        tid = list( tD['testid'] )
        tstL = list( tst )
        assert tid[0] == tstL[0]
        assert tid[2:] == tstL[1:], 'test params not equal: '+str(tid[2:])+' != '+str(tstL[1:])


def get_latest_results_filename():
    ""
    testingdir = os.environ['TESTING_DIRECTORY']
    if os.path.samefile( os.getcwd(), testingdir ):
        testingdir = ''
    else:
        testingdir += '/'

    fnL = []
    for fn in glob.glob( testingdir+'vvtresults.*' ):
        fnL.append( ( os.path.getmtime(fn), fn ) )

    fnL.sort()

    return fnL[-1][1]


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
                    testinfo.append( (D['testid'],D) )

    testinfo.sort()

    return fileinfo, [ tup[1] for tup in testinfo ]
