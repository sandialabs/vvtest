#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os
import subprocess
import time
import string


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

    def addTest(self, name, **attrs):
        """
            name      : name of the test
            prefix    : the "Path" value in the submission; thats all I know
            status    : "passed" or "failed" or "notrun"
            command   : the test command line, but can be anything
            runtime   : number of seconds
            output    : multi-line test output
            exitcode  : something like "Completed" or "Failed"
            exitvalue : typically an integer, such as 0 or 1
        """
        results = {
                 'name' : name,
               'prefix' : attrs.pop( 'prefix'    , '.' ),
               'status' : attrs.pop( 'status'    , 'passed' ),
              'command' : attrs.pop( 'command'   , '' ),
              'runtime' : attrs.pop( 'runtime'   , None ),
               'detail' : attrs.pop( 'detail'    , '' ),
               'output' : attrs.pop( 'output'    , '' ),
             'exitcode' : attrs.pop( 'exitcode'  , None ),
            'exitvalue' : attrs.pop( 'exitvalue' , None ),
        }
        assert len( attrs ) == 0, 'unexpected attribute(s): '+str(attrs)
        self.tests.append( results )

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

    def __init__(self):
        ""
        self.url = None
        self.proj = None
        self.meth = None

    def setDestination(self, cdash_url, project_name, method=None):
        ""
        self.url = cdash_url
        self.proj = project_name

        if not method:
            method = 'urllib'
        assert method.startswith('urllib') or method.startswith('curl')
        self.meth = method

    def send(self, filename):
        ""
        submit_url = self.url.rstrip('/')+'/submit.php'
        submit_url += '?project='+self.proj

        with set_environ( http_proxy='', HTTP_PROXY='',
                          https_proxy='', HTTPS_PROXY='' ):

            if self.meth.startswith('urllib'):
                self.urllib_submit( submit_url, filename )
            else:
                self.curl_submit( self.meth, submit_url, filename )

    def urllib_submit(self, submit_url, filename):
        """
        for python3, the CA cert file can be given to the urlopen command with a kwarg, for example,
            cafile='/etc/pki/tls/certs/ca-bundle.crt'
        but that means adding a mechanism to manage where/how to get/find the CA file
        """
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

    def curl_submit(self, curlcmd, submit_url, filename):
        ""
        cmd = curlcmd+' -T '+filename+' '+submit_url
        print ( cmd )
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

    for results in testlist:
        simple_element( fp, 'Test', results['prefix']+'/'+results['name'] )

    end_element( fp, 'TestList' )

    for results in testlist:
        write_test_result( fp, results )


def write_test_result( fp, results ):
    ""
    start_element( fp, 'Test', Status=results['status'] )

    simple_element( fp, 'Name', results['name'] )
    simple_element( fp, 'Path', results['prefix'] )
    simple_element( fp, 'FullName', results['prefix']+'/'+results['name'] )
    if results['command']:
        simple_element( fp, 'FullCommandLine', results['command'] )

    start_element( fp, 'Results' )

    if results['runtime'] != None:
        write_float_measurement( fp, 'Execution Time', results['runtime'] )

    if results['detail']:
        write_string_measurement( fp, 'Completion Status', results['detail'] )

    if results['exitcode'] != None:
        write_string_measurement( fp, 'Exit Code', results['exitcode'] )

    if results['exitvalue'] != None:
        write_string_measurement( fp, 'Exit Value', results['exitvalue'] )

    if results['output']:
        write_measurement( fp, results['output'] )

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
        fp.write( ' '+n+'="'+attr_escape(v)+'"' )
    fp.write( '>\n' )


def end_element( fp, elmt_name ):
    ""
    fp.write( '</'+elmt_name+'>\n' )


def write_xml_header( fp ):
    ""
    fp.write( '<?xml version="1.0" encoding="UTF-8"?>\n' )


def simple_element( fp, name, value ):
    ""
    fp.write( '<'+name+'>'+escape(value)+'</'+name+'>\n' )


charmap = {}

for i in range(256):
    c = chr(i)
    if c in string.printable or c == '\n':
        charmap[c] = c
    elif c == '\t':
        charmap[c] = ' '
    else:
        charmap[c] = ''

charmap['>'] = '&gt;'
charmap['<'] = '&lt;'
charmap['"'] = '&quot;'
charmap["'"] = '&apos;'
charmap['&'] = '&amp;'

def escape( buf ):
    """
        > is &gt;
        < is &lt;
        " is &quot;
        ' is &apos;
        & is &amp;
    """
    buf2 = ''
    for c in buf:
        buf2 += charmap.get( c, '?' )

    return buf2


def attr_escape( buf ):
    ""
    return escape( buf ).replace( '\n', ' ' )


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
