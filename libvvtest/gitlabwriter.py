#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys
import time
from os.path import join as pjoin

from . import outpututils
print3 = outpututils.print3

import gitinterface
import gitresults


class GitLabWriter:

    def __init__(self, destination, results_test_dir, permsetter):
        ""
        if is_gitlab_url( destination ):
            self.outurl = destination
            self.outdir = None
        else:
            self.outurl = None
            self.outdir = os.path.normpath( os.path.abspath( destination ) )

        self.testdir = results_test_dir
        self.permsetter = permsetter

        self.sortspec = None
        self.datestamp = None
        self.onopts = []
        self.nametag = None

        self.period = 60*60

    def setSortingSpecification(self, sortspec):
        ""
        self.sortspec = sortspec

    def setOutputDate(self, datestamp):
        ""
        self.datestamp = datestamp

    def setNamingTags(self, option_list, name_tag):
        ""
        self.onopts = option_list
        self.nametag = name_tag

    def setOutputPeriod(self, period_in_seconds):
        ""
        self.period = period_in_seconds

    def prerun(self, atestlist, rtinfo, verbosity):
        ""
        if self.outurl:
            self._dispatch_submission( atestlist, rtinfo )
            self.tlast = time.time()

    def midrun(self, atestlist, rtinfo):
        ""
        if self.outurl and time.time()-self.tlast > self.period:
            self._dispatch_submission( atestlist, rtinfo )
            self.tlast = time.time()

    def postrun(self, atestlist, rtinfo, rtconfig=None):
        ""
        if self.outurl:
            self._dispatch_submission( atestlist, rtinfo )
        else:
            self._write_files( atestlist, rtinfo )

    def info(self, atestlist, rtinfo):
        ""
        if self.outurl:
            self._dispatch_submission( atestlist, rtinfo )
        else:
            self._write_files( atestlist, rtinfo )

    def _write_files(self, atestlist, rtinfo):
        ""
        if not os.path.isdir( self.outdir ):
            os.mkdir( self.outdir )

        try:
            self._convert_files( self.outdir, atestlist, rtinfo )
        finally:
            self.permsetter.recurse( self.outdir )

    def _convert_files(self, destdir, atestlist, rtinfo):
        ""
        tcaseL = atestlist.getActiveTests( self.sortspec )

        print3( "Writing", len(tcaseL),
                "tests in GitLab format to", destdir )

        conv = GitLabMarkDownConverter( self.testdir, destdir )
        conv.saveResults( tcaseL, rtinfo )

    def _dispatch_submission(self, atestlist, rtinfo):
        ""
        try:
            start,sfx,msg = make_submit_info( rtinfo, self.onopts, self.nametag )
            epoch = self._submission_epoch( start )

            gr = gitresults.GitResults( self.outurl, self.testdir )
            try:
                rdir = gr.createBranchLocation( directory_suffix=sfx,
                                                epochdate=epoch )
                self._convert_files( rdir, atestlist, rtinfo )
                gr.pushResults( msg )
            finally:
                gr.cleanup()

        except Exception as e:
            print3( '\n*** WARNING: error submitting GitLab results:',
                    str(e), '\n' )

    def _submission_epoch(self, start):
        ""
        if self.datestamp:
            epoch = self.datestamp
        else:
            epoch = start

        return epoch


def make_submit_info( rtinfo, onopts, nametag ):
    ""
    start = rtinfo.getInfo( 'startepoch' )

    sfxL = []

    plat = rtinfo.getInfo( 'platform', None )
    if plat:
        sfxL.append( plat )

    sfxL.extend( onopts )

    if nametag:
        sfxL.append( nametag )

    sfx = '.'.join( sfxL )

    msg = 'vvtest results auto commit '+time.ctime()

    return start,sfx,msg


def is_gitlab_url( destination ):
    ""
    if os.path.exists( destination ):
        return False
    elif gitinterface.repository_url_match( destination ):
        return True
    else:
        return False


class GitLabFileSelector:
    def include(self, filename):
        ""
        bn,ext = os.path.splitext( filename )
        return ext in [ '.vvt', '.xml', '.log', '.txt', '.py', '.sh' ]


class GitLabMarkDownConverter:

    def __init__(self, test_dir, destdir,
                       max_KB=10,
                       big_table_size=100,
                       max_links_per_table=200 ):
        ""
        self.test_dir = test_dir
        self.destdir = destdir
        self.max_KB = max_KB
        self.big_table = big_table_size
        self.max_links = max_links_per_table

        self.selector = GitLabFileSelector()

    def saveResults(self, tcaseL, rtinfo):
        ""
        parts = outpututils.partition_tests_by_result( tcaseL )

        fname = pjoin( self.destdir, 'README.md' )

        with open( fname, 'w' ) as fp:

            write_run_attributes( fp, rtinfo )

            for result in [ 'fail', 'diff', 'timeout',
                            'pass', 'notrun', 'notdone' ]:
                altname = pjoin( self.destdir, result+'_table.md' )
                write_gitlab_results( fp, result, parts[result], altname,
                                      self.big_table, self.max_links )

        for result in [ 'fail', 'diff', 'timeout' ]:
            for i,tcase in enumerate( parts[result] ):
                if i < self.max_links:
                    self.createTestFile( tcase )

    def createTestFile(self, tcase):
        ""
        base = sanitize_path_name( tcase.getSpec().getDisplayString() )
        fname = pjoin( self.destdir, base+'.md' )

        xdir = tcase.getSpec().getExecuteDirectory()
        srcdir = pjoin( self.test_dir, xdir )

        result = outpututils.XstatusString( tcase, self.test_dir, os.getcwd() )
        preamble = 'Name: '+tcase.getSpec().getName()+'  \n' + \
                   'Result: <code>'+result+'</code>  \n' + \
                   'Run directory: ' + os.path.abspath(srcdir) + '  \n'

        self.createGitlabDirectoryContents( fname, preamble, srcdir )

    def createGitlabDirectoryContents(self, filename, preamble, srcdir):
        ""
        with open( filename, 'w' ) as fp:

            fp.write( preamble + '\n' )

            try:
                stream_gitlab_files( fp, srcdir, self.selector, self.max_KB )

            except Exception:
                xs,tb = outpututils.capture_traceback( sys.exc_info() )
                fp.write( '\n```\n' + \
                    '*** error collecting files: '+srcdir+'\n'+tb + \
                    '```\n' )


def write_run_attributes( fp, rtinfo ):
    ""
    nvL = list( rtinfo.asDict().items() )
    nvL.sort()
    for name,value in nvL:
        fp.write( '* '+name+' = '+str(value)+'\n' )

    tm = time.time()
    fp.write( '* currentepoch = '+str(tm)+'\n' )

    t0 = rtinfo.getInfo( 'startepoch', None )
    t1 = rtinfo.getInfo( 'finishepoch', None )
    if t0 and t1:
        fp.write( '* elapsed = '+outpututils.pretty_time( t1-t0 )+'\n' )

    fp.write( '\n' )


def write_gitlab_results( fp, result, testL, altname,
                              maxtablesize, max_path_links ):
    ""
    hdr = '## Tests that '+result+' = '+str( len(testL) ) + '\n\n'
    fp.write( hdr )

    if len(testL) == 0:
        pass

    elif len(testL) <= maxtablesize:
        write_gitlab_results_table( fp, result, testL, max_path_links )

    else:
        bn = os.path.basename( altname )
        fp.write( 'Large table contained in ['+bn+']('+bn+').\n\n' )
        with open( altname, 'w' ) as altfp:
            altfp.write( hdr )
            write_gitlab_results_table( altfp, result, testL, max_path_links )


def write_gitlab_results_table( fp, result, testL, max_path_links ):
    ""
    fp.write( '| Result | Date   | Time   | Path   |\n' + \
              '| ------ | ------ | -----: | :----- |\n' )

    for i,tcase in enumerate(testL):
        add_link = ( i < max_path_links )
        fp.write( format_gitlab_table_line( tcase, add_link ) + '\n' )

    fp.write( '\n' )


def format_gitlab_table_line( tcase, add_link ):
    ""
    tspec = tcase.getSpec()

    result = tcase.getStat().getResultStatus()
    dt = outpututils.format_test_run_date( tcase )
    tm = outpututils.format_test_run_time( tcase )
    displ = tspec.getDisplayString()

    makelink = ( add_link and result in ['diff','fail','timeout'] )

    if not tm:
        tm = '-'

    s = '| '+result+' | '+dt+' | '+tm+' | '
    s += format_test_path_for_gitlab( displ, makelink ) + ' |'

    return s


def format_test_path_for_gitlab( path, makelink ):
    ""
    if makelink:
        repl = sanitize_path_name( path )
        return '['+path+']('+repl+'.md)'
    else:
        return path


def sanitize_path_name( path ):
    ""
    return path.replace( os.sep, '_' ).replace( ' ', '_' )


def stream_gitlab_files( fp, srcdir, selector, max_KB ):
    ""

    files,namewidth = get_directory_file_list( srcdir )

    for fn in files:
        fullfn = pjoin( srcdir, fn )

        incl = selector.include( fullfn )
        meta = get_file_meta_data_string( fullfn, namewidth )

        fp.write( '\n' )
        write_gitlab_formatted_file( fp, fullfn, incl, meta, max_KB )


def get_directory_file_list( srcdir ):
    ""
    maxlen = 0
    fL = []
    for fn in os.listdir( srcdir ):
        fL.append( ( os.path.getmtime( pjoin( srcdir, fn ) ), fn ) )
        maxlen = max( maxlen, len(fn) )
    fL.sort()
    files = [ tup[1] for tup in fL ]

    namewidth = min( 30, max( 10, maxlen ) )

    return files, namewidth


def write_gitlab_formatted_file( fp, filename, include_content, label, max_KB ):
    ""
    fp.write( '<details>\n' + \
              '<summary><code>'+label+'</code></summary>\n' + \
              '\n' + \
              '```\n' )

    if include_content:
        try:
            buf = outpututils.file_read_with_limit( filename, max_KB )
        except Exception:
            xs,tb = outpututils.capture_traceback( sys.exc_info() )
            buf = '*** error reading file: '+str(filename)+'\n' + tb

        if buf.startswith( '```' ):
            buf = buf.replace( '```', "'''", 1 )
        buf = buf.replace( '\n```', "\n'''" )

    else:
        buf = '*** file not archived ***'

    fp.write( buf )

    if not buf.endswith( '\n' ):
        fp.write( '\n' )

    fp.write( '```\n' + \
              '\n' + \
              '</details>\n' )


def get_file_meta_data_string( filename, namewidth ):
    ""
    bn = os.path.basename( filename )

    try:

        fmt = "%-"+str(namewidth)+'s'
        if os.path.islink( filename ):
            fname = os.readlink( filename )
            meta = fmt % ( bn + ' -> ' + fname )
            if not os.path.isabs( fname ):
                d = os.path.dirname( os.path.abspath( filename ) )
                fname = pjoin( d, fname )
        else:
            fname = filename
            meta = fmt % bn

        fsize = os.path.getsize( fname )
        meta += " %-12s" % ( ' size='+str(fsize) )

        fmod = os.path.getmtime( fname )
        meta += ' ' + time.ctime( fmod )

    except Exception:
        meta += ' *** error: '+str( sys.exc_info()[1] )

    return meta
