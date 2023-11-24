#!/usr/bin/env python

import os, sys
from os.path import join as pjoin
from os.path import basename
import time
import tempfile
import shutil
import re

from . import logger
from .gitinterface import GitInterfaceError
from .gitinterface import clone_repo, get_remote_branches
from .gitinterface import change_directory


class GitResults:

    def __init__(self, results_repo_url, working_directory=None):
        ""
        self.git = clone_results_repo( results_repo_url,
                                       working_directory,
                                       'master' )

    def getCloneDirectory(self):
        ""
        return self.git.get_toplevel()

    def createBranchLocation(self, directory_suffix='',
                                   epochdate=None,
                                   granularity='month'):
        ""
        branch,self.subdir = branch_name_and_directory(
                                directory_suffix,
                                epochdate,
                                granularity )

        logger.info( 'Using directory', self.subdir, 'on branch', branch )

        rdir = get_results_orphan_branch( self.git, branch, self.subdir )
        assert os.path.isdir( rdir )

        return rdir

    def pushResults(self, message):
        ""
        branch = self.git.get_branch()

        logger.info( 'Pushing results...' )
        self.git.add( self.subdir )
        self.git.commit( message )
        resilient_commit_push( self.git )

        return branch

    def cleanup(self):
        ""
        check_remove_directory( self.git.get_toplevel() )


class GitResultsReader:

    def __init__(self, results_repo_url, working_directory=None):
        ""
        self.git = clone_results_repo( results_repo_url, working_directory )

    def iterateDirectories(self):
        ""
        top = self.git.get_toplevel()

        for branch in self.iterateBranches():
            self.git.checkout_branch( branch )
            for dn in self._iterate_results_dirs( top ):
                yield branch,dn

    def iterateBranches(self):
        ""
        url = self.git.get_remote_URL()
        for branch in get_remote_branches( url ):
            if GitResultsReader.branchpat.match( branch ):
                yield branch

    def cleanup(self):
        ""
        check_remove_directory( self.git.get_toplevel() )

    branchpat = re.compile( 'results_2[01][0-9][0-9]_[0123][0-9]' )
    dirpat = re.compile( '2[01][0-9][0-9]_[0123][0-9].*' )

    def _iterate_results_dirs(self, topdir):
        ""
        for pn in os.listdir( topdir ):
            if GitResultsReader.dirpat.match( pn ):
                dn = pjoin( topdir, pn )
                if self._summary_file_exists( dn ):
                    yield dn

    def _summary_file_exists(self, dirname):
        """
        a README.md has been used since Aug 2019, before it was TestResults.md
        """
        fn1 = pjoin( dirname, 'README.md' )
        fn2 = pjoin( dirname, 'TestResults.md' )
        if os.path.isfile( fn1 ) or os.path.isfile( fn2 ):
            return True
        else:
            return False


class ResultsSummary:

    def __init__(self, giturl, branch, results_directory):
        ""
        self.url = giturl
        self.branch = branch
        self.rdir = results_directory

        self.cnts = {}
        self.anchors = {}

        self.attrs = {}
        self._parse_readme()

    def getDateStamp(self):
        ""
        ts = basename( self.rdir ).split('.',1)[0]
        tm = time.mktime( time.strptime( ts, "%Y_%m_%d_%H" ) )
        return tm

    def getResultsSubdirectory(self):
        ""
        return basename( self.rdir )

    def getResultsBranch(self):
        ""
        return self.branch

    def getLabel(self):
        ""
        ls = basename( self.rdir ).split('.',1)[1]
        return ls

    def getElapsedTime(self):
        ""
        try:
            elap = get_elapsed_time( self.attrs )
        except Exception:
            elap = 0

        return elap

    def isFinished(self):
        ""
        return 'finishepoch' in self.attrs or 'finishdate' in self.attrs

    def getCounts(self):
        ""
        return self.cnts

    def getResultsLink(self, result=None):
        """
        https://gitlab.cool.com/space/proj/blob/branch/resultsdir/README.md
            #tests-that-pass-34
        """
        loc = map_git_url_to_web_url( self.url )

        bdir = basename( self.rdir )
        lnk = pjoin( loc, 'blob', self.branch, bdir, self.readme )

        if result:
            lnk += '#tests-that-'+result.lower()+'-'+str( self.cnts[result] )

        return lnk

    def _parse_readme(self):
        ""
        self.readme,fn = probe_readme_name( self.rdir )

        with open( fn, 'rt' ) as fp:
            for line in fp:
                try:
                    if line.startswith( ResultsSummary.cntmark ):
                        res,cnt = header_line_result_and_count( line )
                        self.cnts[res] = cnt
                        self.anchors[res] = header_line_to_anchor( line )
                    elif line.startswith( '* ' ):
                        parse_key_value( line, self.attrs )
                except Exception:
                    pass

    cntmark = '## Tests that '
    mlen = len( cntmark )


def map_git_url_to_web_url( giturl ):
    ""
    loc = giturl
    if giturl.endswith( '.git' ):
        loc = giturl[:-4]

    if loc.startswith( 'git@' ):
        loc = loc[4:]
        apL = loc.split( ':', 1 )
        if len(apL) == 2:
            loc = '/'.join( apL )
        loc = 'https://'+loc

    return loc


def get_results_orphan_branch( git, branch, subdir ):
    ""
    with change_directory( git.get_toplevel() ):

        if branch in get_remote_branches( git.get_remote_URL() ):

            git.checkout_branch( branch )

            if not os.path.exists( subdir ):
                os.mkdir( subdir )

        else:
            create_orphan_branch( git, branch, subdir )

        rdir = os.path.abspath( subdir )

    return rdir


def check_remove_directory( dirpath ):
    ""
    if os.path.exists( dirpath ):
        logger.info( 'rm -r '+dirpath )
        shutil.rmtree( dirpath )


def branch_name_and_directory( subdir_suffix='',
                               epochdate=None,
                               granularity='month'):
    ""
    assert granularity == 'month'

    if epochdate == None:
        epochdate = time.time()

    tup = time.localtime(epochdate)
    branch = time.strftime( "results_%Y_%m", tup )
    subdir = time.strftime( "%Y_%m_%d_%H", tup )

    if subdir_suffix:
        subdir += '.'+subdir_suffix

    return branch, subdir


def create_orphan_branch( git, branchname, resultsdir ):
    ""
    tmpdir = tempfile.mkdtemp( '.gitresults' )
    try:
        rdir = os.path.join( tmpdir, resultsdir )
        rfile = os.path.join( rdir, '.create' )

        os.mkdir( rdir )

        with open( rfile, 'w' ) as fp:
            fp.write( time.ctime() + '\n' )

        cmtmsg = "Start results branch"
        git.create_remote_orphan_branch( branchname, cmtmsg, rdir )

    finally:
        shutil.rmtree( tmpdir )


def clone_results_repo( giturl, working_directory, branch=None ):
    ""
    assert giturl and giturl == giturl.strip()

    if not working_directory:
        working_directory = os.getcwd()

    tmpdir = tempfile.mkdtemp( '', 'gitresults_work_clone_', os.getcwd() )

    logger.info( 'Cloning', giturl, 'into', tmpdir )
    git = clone_repo( giturl, tmpdir, branch='master' )

    return git


def resilient_commit_push( git ):
    ""
    err = ''

    for i in range(3):
        try:
            git.push()
        except GitInterfaceError as e:
            err = str(e)
        else:
            err = ''
            break

        git.pull()

    if err:
        raise GitInterfaceError( 'could not push results: '+err )


def probe_readme_name( resultsdir ):
    ""
    readme = 'README.md'
    fn = pjoin( resultsdir, readme )

    if not os.path.exists( fn ):
        readme = 'TestResults.md'
        fn = pjoin( resultsdir, readme )
        assert os.path.exists( fn ), \
            'A README.md or TestResults.md must exist in '+resultsdir

    return readme,fn


def header_line_result_and_count( line ):
    ""
    res,cnt = line[ ResultsSummary.mlen : ].split('=',1)
    res = res.strip()
    assert res
    cnt = int( cnt )

    return res,cnt


def header_line_to_anchor( line ):
    """
    duplicate (approximately) the GitLab algorithm to make a header anchor
    """
    s1 = line[3:].strip().replace( '=', '' )
    s2 = ' '.join( s1.split() )
    s3 = s2.lower()

    return s3

def parse_key_value( line, attrs ):
    """
    * finishdate = Fri Aug 23 17:21:16 2019
    * finishepoch = 1566602476.19
    * hostname = ceerws1803
    * platform = Linux
    * python = /usr/local/epd/epd-7.3-2/bin/python
    * rundir = /scratch/rrdrake/temp/tmpdir_gitresults_tests/TestResults.Linux
    * startdate = Fri Aug 23 17:21:14 2019
    * startepoch = 1566602474.74
    * vvtest = /home/rrdrake/Projects/scidev/scidev_utils/vvt
    * currentepoch = 1566602476.46
    """
    assert line[:2] == '* '

    kvL = line[2:].split( '=', 1 )
    if len( kvL ) == 2:
        k = kvL[0].strip()
        v = kvL[1].strip()
        if k:
            attrs[k] = v


def get_elapsed_time( attrs ):
    ""
    tstart = attrs.get( 'startepoch', None )
    if tstart:
        tstart = float( attrs['startepoch'] )

        tfin = attrs.get( 'finishepoch', None )
        if tfin:
            return int( float(tfin) - tstart + 0.5 )

        tcur = attrs.get( 'currentepoch', None )
        if tcur and float(tcur) >= tstart:
            return int( float(tcur) - tstart + 0.5 )

    elap = attrs.get( 'elapsed', None )
    if elap != None:
        return int( float(elap) + 0.5 )

    return 0
