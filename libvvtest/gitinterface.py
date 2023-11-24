#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import sys
sys.dont_write_bytecode = True
sys.excepthook = sys.__excepthook__
import os
from os.path import abspath, normpath, basename, dirname
from os.path import join as pjoin
import time
import pipes
import shutil
import tempfile
import subprocess
import re


class GitInterfaceError( Exception ):
    pass


class GitRepo:
    """
    Most functions take the optional 'verbose' keyword argument:

        0 : print nothing (this is the default)
        1 : print the git command
        2 : print the directory and git command, print output upon error
        3 : print the directory, the git command, and the output
    """

    def __init__(self, directory=None, **options):
        """
        If 'directory' is not None, then use it as the local repository.
        Otherwise assume current working directory.
        Options can be 'verbose', 'https_proxy', 'gitexe'.
        """
        verb = options.pop( 'verbose', 0 )

        self.grun = GitRunner( **options )
        self.top = get_repo_toplevel( self.grun, directory, verbose=verb )
        self.grun.setRunDirectory( self.top )

    def get_toplevel(self, verbose=0):
        ""
        return self.top

    def add(self, *files, **kwargs):
        """
        If update=True, then same as git add -u.
        """
        verb = kwargs.pop( 'verbose', 0 )

        if len( files ) > 0:
            _add_files_to_index( self.grun, files, verb )
        elif kwargs.get( 'update', False ):
            self.grun.run( 'add -u', verbose=verb )

    def commit(self, message, verbose=0):
        ""
        self.run( 'commit -m', pipes.quote(message), verbose=verbose )

    def status(self, verbose=0):
        ""
        stats = {
            'commits': [],
            'changed': [],
            'untracked': [],
            'stash': [],
        }

        br = _current_branch_string( self.grun, verbose )
        if br == None:
            stats['branch'] = '<no branch found>'
        else:
            stats['branch'] = br

        _get_commits_ahead( self.grun, stats['commits'], verbose )
        _fill_path_statuses( self.grun, stats, verbose )
        _fill_stash_list( self.grun, stats['stash'], verbose )

        return stats

    def push(self, all_branches=False, all_tags=False,
                   repository=None, verbose=0):
        """
        Pushes current branch by default.
            all_branches=True : push all branches
            all_tags=True : push all tags
            repository=URL : push to this repository (defaults to origin)
        """
        if all_branches or all_tags:
            _push_all( self.grun, all_branches, all_tags, repository, verbose )

        else:
            br = self.get_branch()
            if not br:
                raise GitInterfaceError( 'you must be on a branch to push' )

            _push_branch( self.grun, br, repository, verbose )

    def pull(self, rebase=True, verbose=0):
        ""
        if self.is_bare():
            raise GitInterfaceError( 'cannot pull into a bare repository' )

        curbranch = self.get_branch()

        if curbranch == None:
            raise GitInterfaceError( 'cannot pull when HEAD is detached '
                    ' (which may be due to a previous merge conflict' )

        self.run( 'tag GITINTERFACE_PULL_BACKUP', verbose=verbose )

        try:
            cmd = 'pull' + ( ' --rebase' if rebase else '' )
            self.run( cmd, verbose=verbose )

        except Exception:
            self.run( 'rebase --abort', verbose=verbose )
            self.run( 'reset --hard GITINTERFACE_PULL_BACKUP', verbose=verbose )
            self.run( 'checkout '+curbranch, verbose=verbose )
            self.run( 'tag -d GITINTERFACE_PULL_BACKUP', verbose=verbose )
            raise GitInterfaceError( 'pull failed (probably merge conflict)' )

        self.run( 'tag -d GITINTERFACE_PULL_BACKUP' )

    def get_branch(self, verbose=0):
        """
        The current branch name, or None if in a detached HEAD state.
        """
        br = _current_branch_string( self.grun, verbose )
        if br == None:
            raise GitInterfaceError( 'no branch found in '+str(self.top) )
        elif br.startswith( '(' ):
            return None
        else:
            return br

    def get_branches(self, remotes=False, verbose=0):
        ""
        cmd = 'branch'
        if remotes:
            cmd += ' -r'

        x,out = self.run( cmd, capture=True, verbose=verbose )

        bL = _parse_branch_listing_output( out )

        return bL

    def checkout_branch(self, branchname, verbose=0):
        ""
        if branchname != self.get_branch():
            if branchname in self.get_branches():
                self.run( 'checkout', branchname, verbose=verbose )
            elif branchname in self.get_branches( remotes=True ):
                self.run( 'checkout --track origin/'+branchname, verbose=verbose )
            else:
                url = self.get_remote_URL()
                if url and branchname in _remote_branch_list( self.grun, url,
                                                              verbose=verbose):
                    _fetch_then_checkout_branch( self.grun, branchname, verbose )
                else:
                    raise GitInterfaceError( 'branch does not exist: '+branchname )

    def create_branch(self, branchname, verbose=0):
        ""
        if branchname in self.get_branches():
            raise GitInterfaceError( 'branch already exists: '+branchname )

        self.run( 'checkout -b '+branchname, verbose=verbose )

    def get_remote_URL(self, verbose=0):
        ""
        x,out = self.run( 'config --get remote.origin.url',
                          raise_on_error=False, capture=True,
                          verbose=verbose )
        if x != 0:
            return None
        return out.strip()

    def create_remote_branch(self, branchname, verbose=0):
        """
        Create a branch on the remote, checkout, and track it locally.
        Any local changes are not pushed, but are merged onto the new branch.
        """
        curbranch = self.get_branch()

        url = self.get_remote_URL()
        if not url:
            raise GitInterfaceError( 'no remote URL for origin in config file' )

        if branchname in _remote_branch_list( self.grun, url, verbose=verbose ):
            raise GitInterfaceError(
                    'branch name already exists on remote: '+branchname )

        if curbranch not in self.get_branches( remotes=True ):
            raise GitInterfaceError(
                    'current branch must be tracking a remote: '+curbranch )

        self.run( 'branch', branchname, 'origin/'+curbranch, verbose=verbose )
        self.run( 'checkout', branchname, verbose=verbose )
        self.run( 'push -u origin', branchname, verbose=verbose )
        self.run( 'merge', curbranch, verbose=verbose )

    def create_remote_orphan_branch(self, branchname, message, path0, *paths,
                                          **kwargs):
        """
        Create and push a branch containing a copy of the given paths
        (files and/or directories), with the given intial commit message.
        It will share no history with any other branch.
        """
        verbose = kwargs.get( 'verbose', 0 )

        if not self.get_branch():
            raise GitInterfaceError( 'must currently be on a branch' )

        url = self.get_remote_URL()
        if not url:
            raise GitInterfaceError( 'no remote URL for origin in config file' )

        if branchname in _remote_branch_list( self.grun, url, verbose=verbose ):
            raise GitInterfaceError(
                    'branch name already exists on remote: '+branchname )

        pathlist = [ abspath(p) for p in (path0,)+paths ]

        _make_orphan_branch( self.grun, branchname, message, pathlist, verbose )

    def delete_remote_branch(self, branchname, verbose=0):
        ""
        curbranch = self.get_branch()
        if branchname == curbranch:
            raise GitInterfaceError(
                    'cannot delete current branch: '+branchname )

        url = self.get_remote_URL()
        if not url:
            raise GitInterfaceError( 'no remote URL for origin in config file' )

        if branchname not in _remote_branch_list( self.grun, url, verbose=verbose ):
            raise GitInterfaceError(
                    'branch name does not exist on remote: '+branchname )

        if branchname in self.get_branches():
            self.run( 'branch -d', branchname )

        self.run( 'push --delete origin', branchname, verbose=verbose )

    def get_tags(self, verbose=0):
        ""
        x,out = self.run( 'tag --list --no-column',
                          capture=True, verbose=verbose )

        tagL = []

        for line in out.strip().splitlines():
            tag = line.strip()
            if tag:
                tagL.append( tag )

        tagL.sort()

        return tagL

    def checkout_tag(self, tagname, verbose=0):
        ""
        tagL = self.get_tags( verbose )
        if tagname not in tagL:
            raise GitInterfaceError( 'tag name does not exist: '+repr(tagname) )

        self.run( 'checkout', tagname, verbose=verbose )

    def create_tag(self, tagname, commit_message, verbose=0):
        ""
        if tagname in self.get_tags( verbose=verbose ):
            raise GitInterfaceError( 'tag already exists: '+repr(tagname) )

        self.run( 'tag -m', pipes.quote( commit_message ), tagname,
                  verbose=verbose )

    def is_bare(self, verbose=0):
        ""
        x,out = self.run( 'rev-parse --is-bare-repository',
                          capture=True, verbose=verbose )

        val = out.strip().lower()
        if val == 'true':
            return True
        elif val == 'false':
            return False
        else:
            raise GitInterfaceError(
                        'unexpected response from rev-parse: '+str(out) )

    def run(self, arg0, *args, **kwargs):
        """
        Run a raw git command and return exit status and output.  For example,
        run( 'status', 'myfile' ) would execute "git status myfile" at the
        toplevel of the repository.
        """
        return self.grun.run( arg0, *args, **kwargs )


def create_repo( directory=None, bare=False, **options):
    """
    If 'directory' is not None, it is created and will contain the new repo.
    Otherwise the current directory is used.

    Options can be 'https_proxy', 'gitexe', and 'verbose'.

    Returns a GitRepo object set to the new repo.
    """
    verb = options.pop( 'verbose', 0 )
    grun = GitRunner( **options )

    cmd = 'init'
    if bare:
        cmd += ' --bare'

    if directory:
        cd, name = _split_and_create_directory( directory )
        cmd += ' '+name
        top = normpath( abspath( directory ) )
    else:
        cd = None
        top = os.getcwd()

    grun.run( cmd, chdir=cd, verbose=verb )

    return GitRepo( directory=top, **options )


def clone_repo( url, directory=None, branch=None, bare=False, **options ):
    """
    If 'branch' is None, all branches are fetched.  If a branch name (such
    as "master") then only that branch is fetched.  If 'directory' is not
    None, it will contain the repository.

    Options can be 'verbose', 'https_proxy', 'gitexe'.

    Returns a GitRepo object set to the cloned repository.
    """
    verb = options.pop( 'verbose', 0 )
    grun = GitRunner( **options )

    if branch and bare:
        raise GitInterfaceError( 'cannot bare clone a single branch' )

    if branch:
        top = _branch_clone( grun, url, directory, branch, verb )
    else:
        top = _full_clone( grun, url, directory, bare, verb )

    options['verbose'] = max( 0, verb-1 )
    return GitRepo( top, **options )


def get_remote_branches( url, **options ):
    """
    Get the list of branches on the remote repository 'url' (which can be
    a directory).
    """
    verb = options.pop( 'verbose', 0 )
    grun = GitRunner( **options )

    return _remote_branch_list( grun, url, verb )


def update_repository_mirror( from_url, to_url, work_clone=None, **options ):
    ""
    verb = options.get( 'verbose', 0 )

    if work_clone:

        if os.path.isdir( work_clone ):
            with change_directory( work_clone ):
                work_git = GitRepo( **options )
                _mirror_remote_repo_into_pwd( work_git, from_url, verbose=verb )
                _push_branches_and_tags( work_git, to_url, verbose=verb )

        else:
            work_git = clone_repo( from_url, work_clone, bare=True, **options )
            _push_branches_and_tags( work_git, to_url, verbose=verb )

    else:
        tmpdir = tempfile.mkdtemp( dir=os.getcwd() )

        try:
            work_git = clone_repo( from_url, tmpdir, bare=True, **options )
            _push_branches_and_tags( work_git, to_url, verbose=verb )

        finally:
            shutil.rmtree( tmpdir )


# match the form [user@]host.abc:path/to/repo.git/
scp_like_url = re.compile( r'([a-zA-Z0-9_]+@)?[a-zA-Z0-9_-]+([.][a-zA-Z0-9_-]*)*:' )

def repository_url_match( url ):
    ""
    if url.startswith( 'http://' ) or url.startswith( 'https://' ) or \
       url.startswith( 'ftp://' ) or url.startswith( 'ftps://' ) or \
       url.startswith( 'ssh://' ) or \
       url.startswith( 'git://' ) or \
       url.startswith( 'file://' ):
        return True

    elif scp_like_url.match( url ):
        return True

    return False


def is_a_local_repository( directory, **options ):
    ""
    verb = options.pop( 'verbose', 0 )
    grun = GitRunner( directory, **options )

    return _is_local_repo( grun, directory, verb )


def verify_repository_url( url, **options ):
    ""
    if is_a_local_repository( url, **options ):
        return True

    else:
        verb = options.pop( 'verbose', 0 )
        grun = GitRunner( **options )
        x,out = grun.run( 'ls-remote', url,
                          raise_on_error=False, capture=True, verbose=verb )
        if x == 0:
            return True

    return False


########################################################################

class GitRunner:

    def __init__(self, directory=None, **options):
        ""
        self.chdir = directory
        self.envars = {}

        self.gitexe = options.pop( 'gitexe', 'git' )

        prox = options.pop( 'https_proxy', None )
        if prox:
            self.envars['https_proxy'] = prox
            self.envars['HTTPS_PROXY'] = prox

        if len( options ) > 0:
            raise GitInterfaceError( "unknown options: "+str(options) )

    def run(self, arg0, *args, **kwargs):
        ""
        roe = kwargs.pop( 'raise_on_error', True )
        cap = kwargs.pop( 'capture', False )
        cd = kwargs.pop( 'chdir', self.chdir )
        verbose = kwargs.pop( 'verbose', 0 )

        assert len(kwargs) == 0

        cmd = self.gitexe + ' ' + ' '.join( (arg0,)+args )

        with set_environ( **self.envars ):
            x,out = runcmd( cmd,
                            chdir=cd,
                            raise_on_error=roe,
                            capture=cap,
                            verbose=verbose )

        return x, out

    def setRunDirectory(self, rundir):
        ""
        self.chdir = rundir

    def getRunDirectory(self):
        ""
        return self.chdir


def get_repo_toplevel( gitrun, directory=None, verbose=0 ):
    ""
    if not directory:
        directory = os.getcwd()

    with change_directory( directory ):
        x,top = gitrun.run( 'rev-parse --show-toplevel',
                            raise_on_error=False, capture=True,
                            verbose=verbose )
        top = top.strip()

    if (x == 0 and not top) or \
       (x != 0 and 'fatal: this operation must be run in a work tree' in top):
        top = _find_toplevel_bare_git_repo( directory )
        if basename( top ) == '.git':
            # must be in the .git subdirectory of a clone
            top = dirname( top )
        x = 0  # artificially set to be ok

    if x != 0 or not top:
        raise GitInterfaceError( 'could not determine top level '
                                 '(are you in a Git repo?) '+str(directory) )

    return top


def _find_toplevel_bare_git_repo( directory ):
    ""
    top = ''

    d0 = directory
    while True:
        d1 = dirname( d0 )
        if _is_toplevel_bare_git_repo(d0):
            top = d0
            break
        elif d0 == d1:
            break
        d0 = d1

    return top


def _is_toplevel_bare_git_repo( directory ):
    ""
    obj  = pjoin( directory, 'objects' )
    cfg = pjoin( directory, 'config' )
    if os.path.isdir(obj) and os.path.isfile(cfg):
        return True
    return False


def repo_name_from_url( url ):
    ""
    name = basename( normpath(url) )
    if name.endswith( '.git' ):
        name = name[:-4]
    return name


def _branch_clone( grun, url, directory, branch, verbose ):
    ""
    if not directory:
        directory = repo_name_from_url( url )

    with make_and_change_directory( directory ):
        grun.run( 'init', verbose=verbose )
        grun.run( 'remote add -f -t', branch, '-m', branch, 'origin', url,
                  verbose=verbose )
        grun.run( 'checkout', branch, verbose=verbose )
        top = os.getcwd()

    return top


def _full_clone( grun, url, directory, bare, verbose ):
    ""
    cmd = 'clone'
    if bare:
        cmd += ' --bare'

    if directory:
        if not repository_url_match( url ) and _is_local_repo( grun, url, verbose ):
            url = abspath( url )

        with make_and_change_directory( directory ):
            grun.run( cmd, url, '.', verbose=verbose )
            top = os.getcwd()

    else:
        grun.run( cmd, url, verbose=verbose )

        dname = _repo_directory_from_url( url, bare )

        assert os.path.isdir( dname )
        top = abspath( dname )

    return top


def _repo_directory_from_url( url, bare=False ):
    ""
    name = repo_name_from_url( url )
    if bare:
        return name+'.git'
    else:
        return name


def _add_files_to_index( gitrun, files, verbose ):
    ""
    top = gitrun.getRunDirectory()

    # use first file to determine if paths are relative to the current
    # directory or relative to the toplevel

    if os.path.islink( files[0] ) or os.path.exists( files[0] ):

        if is_subdir( top, '.' ):
            gitrun.run( 'add', *_quote_files(files), chdir=None, verbose=verbose )

        else:
            fL = _make_files_relative_to_toplevel( top, files )
            gitrun.run( 'add', *_quote_files(fL), verbose=verbose )

    else:
        path0 = pjoin( top, files[0] )
        if os.path.islink( path0 ) or os.path.exists( path0 ):
            gitrun.run( 'add', *_quote_files(files), verbose=verbose )

        else:
            # fall back to executing git add in the current directory
            gitrun.run( 'add', *_quote_files(files), chdir=None, verbose=verbose )


def _quote_files( filelist ):
    ""
    return [ pipes.quote(f) for f in filelist ]


def _make_files_relative_to_toplevel( top, files ):
    ""
    top = normpath( abspath( top ) )
    lentop = len(top)

    fL = []
    for path in files:

        if not is_subdir( top, path ):
            raise GitInterfaceError( 'path not in the repository: '+path )

        rel = _chop_root_path( lentop, path )

        fL.append( rel )

    return fL


def _chop_root_path( choplen, path ):
    ""
    npath = normpath( abspath( path ) )
    rel = normpath( npath[choplen:] )

    if rel.startswith( os.path.sep ):
        rel = rel.strip( os.path.sep )

    return rel


def _push_all( gitrun, all_branches, all_tags, repository, verbose ):
    ""
    cmd = 'push'

    if all_branches: cmd += ' --all'
    if all_tags:     cmd += ' --tags'

    if repository:
        cmd += ' '+repository

    gitrun.run( cmd, verbose=verbose )


def _push_branch( gitrun, branch, repository, verbose ):
    ""
    cmd = 'push'

    if repository:
        cmd += ' '+repository+' '+branch
    else:
        cmd += ' origin '+branch

    gitrun.run( cmd, verbose=verbose )


def _parse_branch_listing_output( output ):
    ""
    bL = []

    for line in output.splitlines():

        if line.startswith( '* (' ):
            pass

        elif line.startswith( '* ' ) or line.startswith( '  ' ):
            if ' -> ' not in line:
                line = line[2:]
                if line.startswith( 'origin/' ):
                    line = line[7:]
                bL.append( line )

    bL.sort()

    return bL


def _fetch_then_checkout_branch( gitrun, branchname, verbose ):
    ""
    gitrun.run( 'fetch origin', verbose=verbose )

    x,out = gitrun.run( 'checkout --track origin/'+branchname,
                        raise_on_error=False, capture=True,
                        verbose=verbose )

    if x != 0:
        # try adding the branch in the fetch list
        x,out2 = gitrun.run( 'config --add remote.origin.fetch ' + \
                             '+refs/heads/'+branchname + \
                             ':refs/remotes/origin/'+branchname,
                             raise_on_error=False, capture=True,
                             verbose=verbose )
        out += out2

        if x == 0:
            x,out3 = gitrun.run( 'fetch origin',
                                 raise_on_error=False, capture=True,
                                 verbose=verbose )
            out += out3

            if x == 0:
                x,out4 = gitrun.run( 'checkout --track origin/'+branchname,
                                     raise_on_error=False, capture=True,
                                     verbose=verbose )
                out += out4

        if x != 0:
            if verbose >= 2:
                print3( out )
            raise GitInterfaceError( 'branch appears on remote but ' + \
                            'fetch plus checkout failed: '+branchname )


def _current_branch_string( gitrun, verbose ):
    ""
    if _rebase_in_progress( gitrun, verbose ):
        val = '(rebase in progress, e.g. merge conflict)'

    else:
        x,out = gitrun.run( 'branch --no-color', capture=True, verbose=verbose )

        val = None

        for line in out.splitlines():
            if line.startswith( '* (' ):
                # detatched
                val = line[2:].strip()
                break
            elif line.startswith( '* ' ):
                val = line[2:].strip()
                break

    return val


def _rebase_in_progress( gitrun, verbose ):
    ""
    x,out = gitrun.run( 'status', capture=True,
                                  verbose=verbose,
                                  raise_on_error=False )
    if x == 0:
        for line in out.splitlines():
            line = line.strip()
            if line.startswith( '# You are currently rebasing' ) or \
               line.startswith( 'You are currently rebasing' ) or \
               line.startswith( 'You have unmerged paths' ):
                return True

    return False


def _get_commits_ahead( gitrun, commitlist, verbose ):
    ""
    x,out = gitrun.run( 'status', capture=True, verbose=verbose )

    num = None

    for line in out.splitlines():
        line = line.strip()
        if line.startswith( '# Your branch is ahead of' ) or \
           line.startswith( 'Your branch is ahead of' ):
            lineL = line.split()
            if lineL[-1].startswith('commit'):
                try:
                    num = int( lineL[-2] )
                except Exception:
                    num = None
                else:
                    break

    if num:
        x,out = gitrun.run( 'log -n', str(num), '--format="format:%H %s"',
                            capture=True, verbose=verbose )

        for line in out.splitlines():
            lineL = line.strip().split()
            if len( lineL ) > 0:
                commitlist.append( ( lineL[0], ' '.join( lineL[1:] ) ) )


def _fill_path_statuses( gitrun, statD, verbose ):
    ""
    x,out = gitrun.run( 'status --porcelain', capture=True, verbose=verbose )

    chg = statD['changed']
    unk = statD['untracked']

    for line in out.splitlines():
        lineL = line.strip().split()
        if len( lineL ) > 1:
            fmt,fn = lineL[0],lineL[1]
            if fmt == '??':
                unk.append( fn )
            else:
                chg.append( fn )

    chg.sort()
    unk.sort()


def _fill_stash_list( gitrun, stashlist, verbose ):
    ""
    x,out = gitrun.run( 'stash list', capture=True, verbose=verbose )

    for line in out.splitlines():
        lineL = line.strip().split(':',1)
        if len( lineL ) == 2:
            stashlist.append( ( lineL[0], lineL[1] ) )


class change_directory:

    def __init__(self, directory):
        ""
        self.cwd = os.getcwd()
        self.directory = directory

    def __enter__(self):
        ""
        if self.directory:
            assert os.path.isdir( self.directory )
            os.chdir( self.directory )

    def __exit__(self, type, value, traceback):
        ""
        os.chdir( self.cwd )


class make_and_change_directory( change_directory ):

    def __enter__(self):
        ""
        if not os.path.exists( self.directory ):
            os.makedirs( self.directory )

        change_directory.__enter__( self )


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


def is_subdir( parent, subdir ):
    ""
    subdir = normpath( abspath( subdir ) )

    while True:

        if os.path.samefile( parent, subdir ):
            return True

        d2 = dirname( subdir )

        if d2 == subdir:
            break

        subdir = d2

    return False


def _split_and_create_directory( repo_path ):
    ""
    path,name = os.path.split( normpath( repo_path ) )

    if path == '.':
        path = ''

    if path and not os.path.exists( path ):
        os.makedirs( path )

    return path, name


def _remote_branch_list( gitrun, url, verbose ):
    ""
    x,out = gitrun.run( 'ls-remote --heads', url, capture=True, verbose=verbose )

    bL = []
    for line in out.strip().splitlines():
        lineL = line.strip().split( None, 1 )
        if len( lineL ) == 2:
            if lineL[1].startswith( 'refs/heads/' ):
                bL.append( lineL[1][11:] )

    bL.sort()

    return bL


def _is_local_repo( gitrun, directory, verbose ):
    ""
    if not os.path.isdir( directory ) and os.path.isdir( directory+'.git' ):
        directory += '.git'

    verb = max( 0, verbose-1 )  # reduce verbosity for this check
    try:
        x,out = gitrun.run( 'rev-parse --is-bare-repository', chdir=directory,
                            raise_on_error=False, capture=True, verbose=verb )
    except Exception:
        return False

    if x == 0 and out.strip().lower() in ['true','false']:
        return True

    return False


def _mirror_remote_repo_into_pwd( work_git, remote_url, verbose=0 ):
    ""
    if not work_git.is_bare( verbose=verbose ):
        raise GitInterfaceError( 'work_clone must be a bare repository' )

    work_git.run( 'fetch', remote_url,
                  '"refs/heads/*:refs/heads/*"',
                  '"refs/tags/*:refs/tags/*"',
                  verbose=verbose )


def _push_branches_and_tags( work_git, to_url, verbose=0 ):
    ""
    work_git.push( all_branches=True, repository=to_url, verbose=verbose )
    work_git.push( all_tags=True, repository=to_url, verbose=verbose )


def _make_orphan_branch( gitrun, branch, message, pathlist, verbose ):
    ""
    # newer versions of git have a git checkout --orphan option; the
    # implementation here creates a temporary repo with an initial
    # commit then fetches that into the current repository

    tmpdir = tempfile.mkdtemp( '.gitinterface' )
    try:
        _create_repo_with_files( gitrun, tmpdir, message, pathlist, verbose )

        gitrun.run( 'fetch', tmpdir, 'master:'+branch, verbose=verbose )
        gitrun.run( 'checkout', branch, verbose=verbose )
        gitrun.run( 'push -u origin', branch, verbose=verbose )

    finally:
        shutil.rmtree( tmpdir )


def _create_repo_with_files( gitrun, directory, message, pathL, verbose ):
    ""
    with change_directory( directory ):

        gitrun.run( 'init', chdir=None, verbose=verbose )

        fL = []
        for pn in pathL:
            fn = _copy_path_to_current_directory( pn )
            fL.append( pipes.quote(fn) )

        gitrun.run( 'add', *fL, chdir=None, verbose=verbose )
        gitrun.run( 'commit -m', pipes.quote( message ),
                    chdir=None, verbose=verbose )


def _copy_path_to_current_directory( filepath ):
    ""
    bn = basename( filepath )

    if os.path.islink( filepath ):
        os.symlink( os.readlink( filepath ), bn )
    elif os.path.isdir( filepath ):
        shutil.copytree( filepath, bn, symlinks=True )
    else:
        shutil.copyfile( filepath, bn )

    return bn


def runcmd( cmd, chdir=None,
                 raise_on_error=True,
                 capture=False,
                 verbose=0 ):
    ""
    out = ''
    err = ''
    x = 1

    if verbose >= 2:
        if chdir:
            print3( 'cd', chdir, '\n'+cmd )
        else:
            print3( 'PWD='+os.getcwd(), '\n'+cmd )
    elif verbose == 1:
        print3( cmd )

    collect = ( capture or verbose < 3 )

    with change_directory( chdir ):

        if collect:
            po = subprocess.Popen( cmd, shell=True, stdout=subprocess.PIPE,
                                                    stderr=subprocess.PIPE )
        else:
            po = subprocess.Popen( cmd, shell=True )

        sout,serr = po.communicate()
        x = po.returncode

        if sout != None:
            out = _STRING_(sout)

        if serr != None:
            err = _STRING_(serr)

    if x != 0:
        if collect:
            if verbose >= 2:
                flush_stdout_err( out, err )
            else:
                out += err
        if raise_on_error:
            raise GitInterfaceError( 'Command failed: '+cmd )

    elif collect and verbose >= 3:
        flush_stdout_err( out, err )

    return x,out


def flush_stdout_err( out, err ):
    ""
    for fp,val in [ (sys.stdout,out), (sys.stderr,err) ]:
        if val:
            fp.write( '\n'+val )
            if not val.endswith( os.linesep ):
                fp.write( os.linesep )
            fp.flush()


if sys.version_info[0] < 3:
    def _STRING_(b): return b

else:
    bytes_type = type( ''.encode() )

    def _STRING_(b):
        if type(b) == bytes_type:
            return b.decode()
        return b


def print3( *args ):
    sys.stdout.write( ' '.join( [ str(x) for x in args ] ) + '\n' )
    sys.stdout.flush()
