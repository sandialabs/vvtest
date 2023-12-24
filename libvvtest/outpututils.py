#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys
from os.path import join as pjoin
import time
import traceback

from . import pathutil


def XstatusString( tcase, test_dir, cwd ):
    """
    Returns a formatted string containing the job and its status.
    """
    ref = tcase.getSpec()

    s =  ''

    skipreason = None
    if tcase.getStat().skipTest():
        skipreason = tcase.getStat().getReasonForSkipTest()

    if skipreason:
        s += '%-8s' % 'skip'
    else:
        s += '%-8s' % tcase.getStat().getResultStatus()

    s += ' %7s' % format_test_run_time( tcase )
    s += ' %14s' % format_test_run_date( tcase )

    s += ' ' + location_display_string( ref, test_dir, cwd )

    if skipreason:
        s += ' skip_reason="'+skipreason+'"'

    return s


def location_display_string( tspec, test_dir, cwd ):
    ""
    displ = tspec.getDisplayString()
    loc = pathutil.relative_execute_directory( displ, test_dir, cwd )

    tid = tspec.getTestID()
    if tid.executeDirectoryIsShortened():
        xdir = tspec.getExecuteDirectory()
        xdir = pathutil.relative_execute_directory( xdir, test_dir, cwd )
        loc = xdir + ' -> ' + os.path.basename(loc)

    return loc


def get_log_file_path( testdir, tspec ):
    ""
    fn = tspec.getLogFilename()
    return pjoin( testdir, tspec.getExecuteDirectory(), fn )


def get_test_command_line( logfilename ):
    ""
    cmdmark = 'Command      : '

    if os.path.isfile( logfilename ):
        cmd = '*** could not get command line from log file: '+logfilename
        try:
            with open( logfilename, 'rt' ) as fp:
                for line in fp:
                    if line.startswith( cmdmark ):
                        cmd = line.split( cmdmark, 1 )[1].strip()
                        break
        except Exception:
            pass
    else:
        cmd = '*** unable to get command line (log file missing): '+logfilename

    return cmd


def file_read_with_limit( filename, max_KB ):
    ""
    maxsize = max( 128, max_KB * 1024 )
    fsz = os.path.getsize( filename )

    buf = ''
    if fsz < maxsize:
        with open( filename, 'r' ) as fp:
            buf = fp.read()
    else:
        hdr = int( float(maxsize) * 0.20 + 0.5 )
        bot = fsz - int( float(maxsize) * 0.70 + 0.5 )
        with open( filename, 'r' ) as fp:
            buf = fp.read( hdr )
            buf += '\n\n*** the middle of this file has been removed ***\n\n'
            fp.seek( bot )
            buf += fp.read()

    return buf


def make_date_stamp( testdate, optrdate, timefmt="%Y_%m_%d_%Hh_%Mm_%Ss" ):
    ""
    if optrdate is not None:
        if type( optrdate ) == type(''):
            datestr = optrdate
        else:
            tup = time.localtime( optrdate )
            datestr = time.strftime( timefmt, tup )
    else:
        tup = time.localtime( testdate )
        datestr = time.strftime( timefmt, tup )

    return datestr


def partition_tests_by_result( tcaseL ):
    ""
    parts = { 'fail':[], 'timeout':[], 'diff':[],
              'pass':[], 'notrun':[], 'notdone':[],
              'skip':[] }

    for tcase in tcaseL:
        if tcase.getStat().skipTest():
            parts[ 'skip' ].append( tcase )
        else:
            result = tcase.getStat().getResultStatus()
            parts[ result ].append( tcase )

    return parts


def results_summary_string( testparts ):
    ""
    sumL = []

    for result in [ 'pass', 'fail', 'diff', 'timeout',
                    'notdone', 'notrun', 'skip' ]:
        sumL.append( result+'='+str( len( testparts[result] ) ) )

    return ', '.join( sumL )


def format_test_run_date( tcase ):
    ""
    xdate = tcase.getStat().getStartDate( 0 )
    if xdate > 0:
        return time.strftime( "%m/%d %H:%M:%S", time.localtime(xdate) )
    else:
        return ''


def format_test_run_time( tcase ):
    ""
    xtime = tcase.getStat().getRuntime( -1 )
    if xtime < 0:
        return ''
    else:
        return colon_separated_time( xtime )


def colon_separated_time( nseconds ):
    ""
    hr,mn,sc = get_hour_minute_second( nseconds )
    if hr == 0:
        return '%d:%02d' % (mn,sc)
    return '%d:%02d:%02d' % (hr,mn,sc)


def get_hour_minute_second( nseconds ):
    ""
    h = int( nseconds / 3600 )
    m = int( ( nseconds - 3600*h ) / 60 )
    s = int( ( nseconds - 3600*h - 60*m ) + 0.5 )
    return h,m,s


def pretty_time( nseconds ):
    ""
    h,m,s = get_hour_minute_second( nseconds )
    sh = str(h)+'h'
    sm = str(m)+'m'

    if h == 0 and m == 0 and s == 0:
        s = 1
    ss = str(s) + 's'

    if h > 0: return sh+' '+sm+' '+ss
    if m > 0: return sm+' '+ss
    return ss


def capture_traceback( excinfo ):
    """
    This should be called in an except block of a try/except, and the argument
    should be sys.exc_info().  It extracts and formats the traceback for the
    exception.  Returns a pair ( the exception string, the full traceback ).
    """
    xt,xv,xtb = excinfo
    # the "exception only" function may return multiple lines, but the last
    # line is always the exception description
    xsL = traceback.format_exception_only( xt, xv )
    xs = xsL[-1]
    tb = 'Traceback (most recent call last):\n' + \
         ''.join( traceback.format_list(
                        traceback.extract_stack()[:-2] +
                        traceback.extract_tb( xtb ) ) ) + ''.join( xsL )
    return xs,tb
