#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import sys
sys.dont_write_bytecode = True
sys.excepthook = sys.__excepthook__
import os
import subprocess
import time


class TestResultsFormatter:

    def __init__(self):
        ""
        self.date = None
        self.group = None
        self.site = None
        self.build = None
        self.start = None
        self.end = None
        self.tests = []

    def setBuildID(self, build_date=None,
                         build_group=None,
                         site_name=None,
                         build_name=None ):
        ""
        if build_date  != None: self.date  = int( build_date )
        if build_group != None: self.group = build_group
        if site_name   != None: self.site  = site_name
        if build_name  != None: self.build = build_name

    def setTime(self, start_time, end_time=None):
        ""
        self.start = start_time
        if end_time != None: self.end = end_time

    def addTest(self, name, prefix='.',
                            status='passed',
                            cmdline='',
                            runtime=None,
                            detail='',
                            output='' ):
        ""
        tup = ( name, prefix, status, cmdline, runtime, detail, output )
        self.tests.append( tup )

    def writeToFile(self, filename):
        ""
        dt   = int( time.time() ) if self.date  == None else self.date
        grp  = 'Experimental'     if self.group == None else self.group
        site = os.uname()[1]      if self.site  == None else self.site
        bld  = 'tests'            if self.build == None else self.build

        stamp = make_build_stamp( dt, grp )

        with open( filename, 'wt' ) as fp:

            write_xml_header( fp )

            start_element( fp, 'Site', BuildStamp=stamp,
                                       Name=site,
                                       BuildName=bld,
                                       Append='true' )

            start_element( fp, 'Testing' )
            write_time_section( fp, dt, self.start, self.end )
            write_tests_section( fp, self.tests )
            end_element( fp, 'Testing' )

            end_element( fp, 'Site' )


class FileSubmitter:

    def __init__(self, cdash_url, project_name, method='urllib'):
        ""
        self.url = cdash_url
        self.proj = project_name

        assert method in ['urllib','curl']
        self.meth = method

    def send(self, filename):
        ""
        submit_url = self.url.rstrip('/')+'/submit.php'
        submit_url += '?project='+self.proj

        with set_environ( http_proxy='', HTTP_PROXY='',
                          https_proxy='', HTTPS_PROXY='' ):

            if self.meth == 'urllib':
                self.urllib_submit( submit_url, filename )
            else:
                self.curl_submit( submit_url, filename )

    def urllib_submit(self, submit_url, filename):
        ""
        import urllib

        if hasattr( urllib, 'urlopen' ):
            content = read_file( filename, 'rt' )
            hnd = urllib.urlopen( submit_url, data=content, proxies={} )
            check_submit_response( hnd.getcode(), hnd.info() )
        else:
            # python 3
            from urllib.request import urlopen
            content = read_file( filename, 'rb' )
            hnd = urlopen( submit_url, data=content )
            check_submit_response( hnd.getcode(), hnd.info() )

    def curl_submit(self, submit_url, filename):
        ""
        cmd = 'curl -T '+filename+' '+submit_url
        subprocess.check_call( cmd, shell=True )


def write_time_section( fp, stamp_date, start, end ):
    ""
    if start == None: start = stamp_date
    if end == None: end = start

    elapsed = ( end-start ) / 60

    simple_element( fp, 'StartDateTime', string_date(start) )
    simple_element( fp, 'StartTestTime', str(start) )
    simple_element( fp, 'EndDateTime', string_date(end) )
    simple_element( fp, 'EndTestTime', str(end) )
    simple_element( fp, 'ElapsedMinutes', str(elapsed) )


def write_tests_section( fp, testlist ):
    ""
    start_element( fp, 'TestList' )

    for name,prefix,status,cmdline,runtime,detail,output in testlist:
        simple_element( fp, 'Test', prefix+'/'+name )

    end_element( fp, 'TestList' )

    for results in testlist:
        write_test_result( fp, results )


def write_test_result( fp, results ):
    ""
    name,prefix,status,cmdline,runtime,detail,output = results

    start_element( fp, 'Test', Status=status )

    simple_element( fp, 'Name', name )
    simple_element( fp, 'Path', prefix )
    simple_element( fp, 'FullName', prefix+'/'+name )
    if cmdline:
        simple_element( fp, 'FullCommandLine', cmdline )

    start_element( fp, 'Results' )

    if runtime != None:
        write_float_measurement( fp, 'Execution Time', runtime )

    if detail:
        write_string_measurement( fp, 'Completion Status', detail )

    if output:
        write_measurement( fp, output )

    end_element( fp, 'Results' )
    end_element( fp, 'Test' )


def write_float_measurement( fp, name, value ):
    ""
    start_element( fp, 'NamedMeasurement', type="numeric/double", name=name )
    simple_element( fp, 'Value', str(value) )
    end_element( fp, 'NamedMeasurement' )


def write_string_measurement( fp, name, value ):
    ""
    start_element( fp, 'NamedMeasurement', type="text/string", name=name )
    simple_element( fp, 'Value', str(value) )
    end_element( fp, 'NamedMeasurement' )


def write_measurement( fp, value ):
    ""
    start_element( fp, 'Measurement' )
    simple_element( fp, 'Value', str(value) )
    end_element( fp, 'Measurement' )


def start_element( fp, elmt_name, **kwargs ):
    ""
    fp.write( '<'+elmt_name )
    for n,v in kwargs.items():
        fp.write( ' '+n+'="'+v+'"' )
    fp.write( '>\n' )


def end_element( fp, elmt_name ):
    ""
    fp.write( '</'+elmt_name+'>\n' )


def write_xml_header( fp ):
    ""
    fp.write( '<?xml version="1.0" encoding="UTF-8"?>\n' )


def simple_element( fp, name, value ):
    ""
    fp.write( '<'+name+'>'+value+'</'+name+'>\n' )


def make_build_stamp( epoch, group ):
    ""
    stamp = time.strftime( '%Y%m%d-%H%M%S-', time.localtime(epoch) )
    stamp += group
    return stamp


def string_date( epoch ):
    ""
    return time.strftime( '%b %d %H:%M:%S %Z', time.localtime(epoch) )


def check_submit_response( code, msg ):
    ""
    if code not in [200,'200']:
        res = 'Unexpected response code: '+repr(code)
        for val in msg.headers:
            res += '\n'+val.strip()
        raise Exception( res )


def read_file( filename, mode ):
    ""
    with open( filename, mode ) as fp:
        contents = fp.read()

    return contents


class set_environ:

    def __init__(self, **name_value_pairs):
        """
        If the value is None, the name is removed from os.environ.
        """
        self.pairs = name_value_pairs

    def __enter__(self):
        ""
        self.save_environ = dict( os.environ )

        for n,v in self.pairs.items():
            if v == None:
                if n in os.environ:
                    del os.environ[n]
            else:
                os.environ[n] = v

    def __exit__(self, type, value, traceback):
        ""
        for n,v in self.pairs.items():
            if n in self.save_environ:
                os.environ[n] = self.save_environ[n]
            elif v != None:
                del os.environ[n]
