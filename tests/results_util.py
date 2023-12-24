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

import libvvtest.fmtresults as fmtresults


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


def assert_cat_dog_runtimes( runtimes_dir ):
    ""
    tr = fmtresults.TestResults( runtimes_dir+'/'+fmtresults.runtimes_filename )

    topdir = ''
    assert len( tr.dirList() ) == 1
    assert tr.dirList() == [ topdir+'one' ]
    assert tr.testList(topdir+'one') == ['cat','dog']
    assert tr.testAttrs(topdir+'one','cat')['xtime'] >= 1
    assert tr.testAttrs(topdir+'one','dog')['xtime'] >= 2


def assert_circle_runtimes( runtimes_dir ):
    ""
    tr = fmtresults.TestResults( runtimes_dir+'/'+fmtresults.runtimes_filename )

    topdir = ''
    assert len( tr.dirList() ) == 1
    assert tr.dirList() == [ topdir+'two' ]
    assert tr.testAttrs(topdir+'two','circle')['xtime'] >= 3


def create_runtimes_and_results_file( testresults_dir, testsrcdir=None ):
    """
    Save test results from the 'testresults_dir' to the TESTING_DIRECTORY
    and return the results filename.
    """
    vtu.runvvtest( '-i --save-results', chdir=testresults_dir )
    resultsfname = get_latest_results_filename()
    return resultsfname


def results_write_creates_the_same_file( results_fname, testresults_obj ):
    ""
    platname = testresults_obj.platform()
    cplrname = testresults_obj.compiler()
    mach = os.uname()[1]
    tdir = testresults_obj.testdir()

    testresults_obj.writeResults( results_fname+'.cmp',
                                  platname, cplrname, mach, tdir )

    return filecmp.cmp( results_fname, results_fname+'.cmp' ) == True


def assert_empty_testresults_file( filename ):
    ""
    tr = fmtresults.TestResults( filename )
    assert len( tr.dirList() ) == 0


def assert_results_file_has_tests( filename, *tests, **kwargs ):
    ""
    fileinfo,testinfo = read_results_file( filename )

    # tr = fmtresults.TestResults( filename )

    # topdir = kwargs.pop( 'topdir', None )
    # if topdir == None:
    #     topdir = os.path.basename( os.getcwd() )

    for i,tst in enumerate(tests):
        tD = testinfo[i]
        tid = list( tD['testid'] )
        tstL = list( tst )
        assert tid[0] == tstL[0]
        assert tid[2:] == tstL[1:], 'test params not equal: '+str(tid[2:])+' != '+str(tstL[1:])


def assert_results_file_does_not_have_tests( filename, *tests, **kwargs ):
    ""
    tr = fmtresults.TestResults( filename )

    topdir = kwargs.pop( 'topdir', None )
    if topdir == None:
        topdir = os.path.basename( os.getcwd() )

    for tst in tests:
        rootrel,testkey = os.path.split( topdir+'/'+tst )
        assert len( tr.testAttrs( rootrel, testkey ) ) == 0


def get_results_test_time_from_file( filename, testname ):
    ""
    tr = fmtresults.TestResults( filename )
    return get_results_test_time( tr, testname )


def get_results_test_time( testresults_obj, testname ):
    ""
    rootrel,testkey = os.path.split( testname )
    aD = testresults_obj.testAttrs( rootrel, testkey )

    xtime = aD.get( 'xtime', -1 )

    return xtime


def assert_multi_results_file_has_tests( filename, num_plats, *tests ):
    ""
    mr = fmtresults.MultiResults()
    mr.readFile( filename )

    for tst in tests:
        rootrel,testkey = os.path.split( tst )
        assert len( mr.platformList( rootrel, testkey ) ) == num_plats


def get_multi_results_test_attributes( filename, testname, platid=None ):
    ""
    mr = fmtresults.MultiResults()
    mr.readFile( filename )

    rootrel,testkey = os.path.split( testname )

    pL = mr.platformList( rootrel, testkey )

    if len( pL ) > 0:
        if platid == None:
            platid = pL[0]
        else:
            assert platid in pL

        aD = mr.testAttrs( rootrel, testkey, platid )

        return aD

    else:
        return {}


def get_multi_results_test_time( filename, testname, platid=None ):
    ""
    aD = get_multi_results_test_attributes( filename, testname, platid )

    xtime = aD.get( 'xtime', -1 )

    return xtime


def get_multi_results_test_result( filename, testname, platid=None ):
    ""
    aD = get_multi_results_test_attributes( filename, testname, platid )

    result = aD.get( 'result', '' )

    return result


def get_results_platform_compiler_id( filename ):
    ""
    tr = fmtresults.TestResults( filename )

    platname,cplrname = tr.platform(), tr.compiler()

    if cplrname:
        platcplr = platname+'/'+cplrname
    else:
        platcplr = platname

    return platcplr


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


def rename_results_filename_to_5_days_ago( filename ):
    ""
    nL = filename.split('.')
    tm = time.mktime( time.strptime( nL[1], '%Y_%m_%d' ) )
    d5 = time.strftime( "%Y_%m_%d", time.localtime( tm - 5*24*60*60 ) )
    newfname = '.'.join( [nL[0],d5]+nL[2:] )
    os.rename( filename, newfname )

    return newfname


def compute_yesterdays_date_string():
    ""
    now = datetime.date.today()
    yesterday = now - datetime.timedelta( days=1 )
    return yesterday.strftime( '%Y_%m_%d' )


def copy_results_file_with_new_platid( filename, newfilename, newplatid=None,
                                       newtestdir=None ):
    ""
    tr = fmtresults.TestResults( filename )
    mach = tr.machine()

    if newtestdir:
        tdir = newtestdir
    else:
        tdir = tr.testdir()

    if newplatid:
        plat,cplr = newplatid.split('/')
    else:
        plat,cplr = tr.platform(), tr.compiler()

    tr.writeResults( newfilename, plat, cplr, mach, tdir )


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

