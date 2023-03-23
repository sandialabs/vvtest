#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys
import string
import random
import time
import re
import glob
import shutil

from .deputils import save_test_data, read_test_data
from .exprutils import platform_expr, parameter_expr, option_expr


def analyze_only():
    """
    the --analyze option means only execute operations in the test that
    analyze previously computed results, such as comparing to baseline or
    examining order of convergence
    """
    import vvtest_util as vvt
    return vvt.opt_analyze


############################################################################

# a test can call set_have_diff() one or more times if it
# decides the test should diff, then at the end of the test,
# call if_diff_exit_diff()

have_diff = False

def set_have_diff():
    global have_diff
    have_diff = True

def exit_diff():
    ""
    import vvtest_util as vvt
    print ( "\n*** exiting diff, " + str(vvt.TESTID) )
    sys.stdout.flush() ; sys.stderr.flush()
    os._exit( vvt.diff_exit_status )

def if_diff_exit_diff():
    if have_diff:
        exit_diff()

############################################################################

def register_termination_function( func ):
    """
    Register a function to be called right before the script exits.  Some
    tricks are played here so that the function is not called if the script
    is exiting due to a failure (an uncaught exception).
    """
    global _user_terminate_func_
    _user_terminate_func_ = func
    if func != None:
        import atexit
        atexit.register( _terminate_func_ )
        sys.excepthook = _except_hook_
    else:
        sys.excepthook = sys.__excepthook__

def _except_hook_( exctype, excvalue, tb ):
    """
    An internal function to catch exceptions.  We do this in order to avoid
    calling a user registered termination function when there is an exception.
    This function just increments an exception counter and prints the
    exception message.  It also unsets the exception hook just in case.
    """
    sys.excepthook = sys.__excepthook__
    global _num_exceptions_
    _num_exceptions_ += 1
    import traceback
    traceback.print_exception( exctype, excvalue, tb )
    sys.stdout.flush() ; sys.stderr.flush()

def _terminate_func_():
    """
    An internal function that wraps user registered termination functions.
    The purpose is to check if the shutdown is due to a failure or not.
    If not a failure, the user function is called.
    """
    if _num_exceptions_ == 0 and _user_terminate_func_ is not None:
        _user_terminate_func_()

_user_terminate_func_ = None
_num_exceptions_ = 0

# some pythons hang if the excepthook is not the default, so make sure it is
sys.excepthook = sys.__excepthook__

############################################################################

def set_python_trace( turnon=True ):
    """
    This function sets a hook that traces the execution of python.  It can
    be useful to debug test scripts.
    """
    if turnon:
        sys.settrace( _tracer_ )
    else:
        sys.settrace( None )

import inspect

def _tracer_( frame, event, arg ):
    """
    Internal function for tracing python execution.  Send this function
    into sys.settrace().

    TODO: add a way to select whether files in sys.prefix are traced or not
    TODO: make the the max argument length settable in set_python_trace()
    """
    # the namespace can get weird in some cases and 'inspect' can be None
    if inspect != None:
        
        # this returns (filename, lineno, function, code_context, index)
        infT = inspect.getframeinfo( frame, 1 )
        fileloc = infT[0]+':'+str(infT[1])  # the file name and line
        if infT[3]:
            codeline = infT[3][ infT[4] ].rstrip()  # the relevant line of code
        else:
            codeline = infT[2] if infT[2] else '<unknown>'

        # try to avoid tracing files inside of the python installation
        p1 = os.path.realpath( sys.prefix )
        p2 = os.path.realpath( infT[0] )
        if p2[:len(p1)] == p1:
            return None

        if event == 'call':
            if infT[2] == 'print3':
                return None

            # try to determine if this call was made from a location that is
            # not being traced; if so, write out the line that made the call
            frL = inspect.getouterframes( frame, 1 )
            if len(frL) > 1:
                # the frame list is a list of tuples
                #   (frame obj, filename, line num, func name,
                #    list list, line index )
                frT = frL[1]  # the frame record of the caller
                fr = frT[0]  # the frame instance of the caller
                if hasattr( fr, 'f_trace' ) and fr.f_trace == None:
                    line = frT[4][ frT[5] ].rstrip()
                    floc = frT[1]+':'+str(frT[2])
                    sys.stdout.write( '>>> '+"%-60s"%line+' @ '+floc+'\n' )
            
            # for a call, the arguments to the function are written too
            argT = inspect.getargvalues( frame )
            try:
                args = ' '+inspect.formatargvalues( *argT )
            except:
                args = '(??)'
            if len(args) > 300:
                args = args[:300]+' ...)'  # truncate large argument values
            sys.stdout.write( '>>> '+"%-60s"%codeline+args+' @ '+fileloc+'\n' )
        
        elif event == 'line':
            sys.stdout.write( '>>> '+"%-60s"%codeline+' @ '+fileloc+'\n' )
        
        # return the current function, otherwise tracing deeper into the
        # call stack stops
        return _tracer_

############################################################################

def print3( *args, **kwargs ):
    "a python 2 & 3 compatible print function"
    s = " ".join( [ str(x) for x in args ] )
    if len(kwargs) > 0:
        L = [ str(k)+"="+str(v) for k,v in kwargs.items() ]
        s += " " + " ".join( L )
    sys.stdout.write( s + os.linesep )
    sys.stdout.flush()

############################################################################

def prependPATH( path ):
    """
    Inserts the given directory path to the beginning of the PATH list.
    """
    if 'PATH' in os.environ:
        os.environ['PATH'] = path+':'+os.environ['PATH']
    else:
        os.environ['PATH'] = path

def appendPATH( path ):
    """
    Inserts the given directory path to the end of the PATH list.
    """
    if 'PATH' in os.environ:
        os.environ['PATH'] = os.environ['PATH']+':'+path
    else:
        os.environ['PATH'] = path

############################################################################

def which( program ):
    """
    Returns the full path to the given program name if found in PATH.  If
    not found, None is returned.
    """
    if os.path.isabs( program ):
        return program

    pth = os.environ.get( 'PATH', None )
    if pth:
        for d in pth.split(':'):
            f = os.path.join( d, program )
            if not os.path.isdir(f) and os.access( f, os.X_OK ):
                return f

    return None

############################################################################

def readfile( filename ):
    ""
    with open( filename, 'r' ) as fp:
        buf = fp.read()

    return buf

############################################################################

def sedfile( filename, pattern, replacement, *more ):
    '''
    Apply one or more regex pattern replacements to each
    line of the given file.  If the file is a regular file,
    its contents is replaced.  If the file is a soft link, the
    soft link is removed and a regular file is written with
    the new contents in its place.
    '''
    import re
    assert len(more) % 2 == 0
    
    info = '\nsedfile: filename="'+filename+'":'
    info += ' '+pattern+' -> '+replacement
    prL = [ ( re.compile( pattern ), replacement ) ]
    for i in range( 0, len(more), 2 ):
        info += ', '+more[i]+' -> '+more[i+1]
        prL.append( ( re.compile( more[i] ), more[i+1] ) )
    
    print ( info )

    fpin = open( filename, 'r' )
    fpout = open( filename+'.sedfile_tmp', 'w' )
    line = fpin.readline()
    while line:
        for cpat,repl in prL:
            line = cpat.sub( repl, line )
        fpout.write( line )
        line = fpin.readline()
    fpin.close()
    fpout.close()

    os.remove( filename )
    os.rename( filename+'.sedfile_tmp', filename )

############################################################################

def unixdiff( file1, file2 ):
    '''
    If the filenames 'file1' and 'file2' are different, then
    the differences are printed and set_have_diff() is called.
    Returns True if there is a diff, otherwise False.
    '''
    assert os.path.exists( file1 ), "file does not exist: "+file1
    assert os.path.exists( file2 ), "file does not exist: "+file2
    import filecmp
    print ( '\nunixdiff: diff '+file1+' '+file2 )
    if not filecmp.cmp( file1, file2 ):
        print ( '*** unixdiff: files are different, setting have_diff' )
        set_have_diff()
        fp1 = open( file1, 'r' )
        flines1 = fp1.readlines()
        fp2 = open( file2, 'r' )
        flines2 = fp2.readlines()
        import difflib
        diffs = difflib.unified_diff( flines1, flines2,
                                      file1, file2 )
        fp1.close()
        fp2.close()
        sys.stdout.writelines( diffs )
        sys.stdout.flush()
        return True
    return False

############################################################################

def nlinesdiff( filename, maxlines ):
    '''
    Counts the number of lines in 'filename' and if more
    than 'maxlines' then have_diff is set and True is returned.
    Otherwise, False is returned.
    '''
    fp = open( filename, 'r' )
    n = 0
    line = fp.readline()
    while line:
        n += 1
        line = fp.readline()
    fp.close()

    print ( '\nnlinesdiff: filename = '+filename + \
            ', num lines = '+str(n) + \
            ', max lines = '+str(maxlines) )
    if n > maxlines:
        print ( '*** nlinesdiff: number of lines exceeded '
                'max, setting have_diff' )
        set_have_diff()
        return True
    return False

############################################################################

def runcmd( cmd, echo=True, ignore_exit=False, capture_output=False,
                 redirect=None, append=False ):
    """
    Execute a command as a subprocess and wait for it to finish.

    If the exit status is non-zero and 'ignore_exit' is False, then
    an exception is raised.

    If 'capture_output' is True, then stdout & stderr is captured and
    returned in a string.

    If 'redirect' is a file name, then stdout & stderr goes to the file.
    If 'append' is True, then 'redirect' appends to the file rather than
    overwriting it.  Using 'redirect' cancels 'capture_output'.
    
    If 'capture_output' is True, then the output is returned (a string).
    Otherwise the exit status is returned.
    """
    import subprocess
    
    if type(cmd) != type(''):
        # assume a list; note that the quoting prevents shell expansions
        cmd = '"' + '" "'.join( cmd ) + '"'
    
    opts = {}

    outfp = fdout = None
    if redirect != None:
        capture_output = False
        if append:
            outfp = open( redirect, "a" )
        else:
            outfp = open( redirect, "w" )
        fdout = outfp.fileno()
        opts['stdout'] = fdout
        opts['stderr'] = subprocess.STDOUT
    
    elif capture_output:
        opts['stdout'] = subprocess.PIPE
        opts['stderr'] = subprocess.STDOUT
    
    if echo:
        if outfp == None:
            sys.stdout.write( cmd + '\n' )
        else:
            sys.stdout.write( cmd + ' > ' + redirect + '\n' )
        sys.stdout.flush()
    
    opts['shell'] = True

    # Setting `stdin` to something is necessary because if it is left unset,
    # it inherits the file handles from the parent. So, sometimes when you use
    # `subprocess.call()` to run something with mpiexec, the process will hang
    # after finishing and never return. Close devnull after call().
    #
    # If we only supported python3.3+, we could just set it to
    # `subprocess.DEVNULL` and be done with it.
    infp = open(os.devnull, 'r')
    opts['stdin'] = infp

    if capture_output:
        proc = subprocess.Popen( cmd, **opts )
        out = proc.communicate()[0]
        if sys.version_info[0] > 2:
            out = out.decode()
        x = proc.returncode
    else:
        x = subprocess.call( cmd, **opts )

    infp.close()
    if outfp != None:
        outfp.close()
    outfp = fdout = None

    if not ignore_exit and x != 0:
        raise Exception( 'command failed: '+cmd )

    if capture_output:
        return out
    return x

############################################################################

def catfile( filename ):
    """
    Reads the given file name and writes it to stdout.
    """
    fp = open( filename, 'r' )
    try:
        line = fp.readline()
        while line:
            sys.stdout.write( line )
            line = fp.readline()
    except:
        fp.close()
        raise
    fp.close()
    sys.stdout.flush()

def grepfile( regex_pattern, filename ):
    """
    Searches the file 'filename' line-by-line for a regular expression pattern.
    Returns a list of strings of the lines that matched.

    TODO: could allow 'filename' to be a glob pattern
    """
    import re
    pat = re.compile( regex_pattern )

    L = []
    fp = open( filename, 'r' )
    try:
        line = fp.readline()
        while line:
            line = line.rstrip()
            if pat.search( line ):
                L.append( line )
            line = fp.readline()
    except:
        fp.close()
        raise

    fp.close()

    return L

############################################################################

def get_permissions( path_or_fmode, which ):
    """
    Given a file path name and a specification string, returns True/False.
    The specification for 'which':

        read    : True if the file has read permission
        write   : True if the file has write permission
        execute : True if the file has execute permission

        setuid  : True if the file is marked set-uid

        owner <mode> : True if the file satisfies the given mode for owner
        group <mode> : True if the file satisfies the given mode for group
        world <mode> : True if the file satisfies the given mode for world

    where <mode> specifies the file mode, such as rx, rwx, r-x, r, w, x, s.
    If a minus sign is in the <mode> then an exact match of the file mode
    must be true for this function to return True.

    The 'path_or_fmode' can be an integer file mode instead of a path, but
    can only be a file path if 'which' is "read", "write" or "execute".
    """
    if which == 'read':
        assert type(path_or_fmode) == type('')
        return os.access( path_or_fmode, os.R_OK )
    
    elif which == 'write':
        assert type(path_or_fmode) == type('')
        return os.access( path_or_fmode, os.W_OK )
    
    elif which == 'execute':
        assert type(path_or_fmode) == type('')
        return os.access( path_or_fmode, os.X_OK )
    
    else:
        
        import stat
        if type(path_or_fmode) == type(2):
            fmode = path_or_fmode
        else:
            fmode = filemode( path_or_fmode )

        if which == 'setuid':
            return True if ( fmode & stat.S_ISUID ) else False

        elif which.startswith( 'owner ' ):
            owner_mask, owner_bits = get_owner_bits()
            s = which.split()[1]
            if '-' in s:
                return (fmode & owner_mask) == owner_bits[s]
            return (fmode & owner_bits[s]) == owner_bits[s]
        
        elif which.startswith( 'group ' ):
            group_mask, group_bits = get_group_bits()
            s = which.split()[1]
            if '-' in s:
                return (fmode & group_mask) == group_bits[s]
            return (fmode & group_bits[s]) == group_bits[s]
        
        elif which.startswith( 'world ' ):
            world_mask, world_bits = get_world_bits()
            s = which.split()[1]
            if '-' in s:
                return (fmode & world_mask) == world_bits[s]
            return (fmode & world_bits[s]) == world_bits[s]
        
        raise Exception( "unknown 'which' value: "+str(which) )


def change_permissions( pathname, spec, *more_specs ):
    """
    Modifies the file path name permissions according to 'spec'.

    A specification is a string with format

        {u|g|o}{=|+|-}{one two or three letter sequence}

    where

        the first character: u=user/owner, g=group, o=other/world
        the second character: '=' means set, '+' means add, '-' means remove
        the permission characters: r=read, w=write, x=execute, s=sticky

    For example, "u+x" means add user execute permission, and "g=rx" means
    set the group permissions to exactly read, no write, execute.

    Additional specifications can be given as separate arguments.
    """
    m = filemode( pathname )
    m = change_filemode( m, *( (spec,)+more_specs ) )
    os.chmod( pathname, m )


def filemode( path ):
    """
    Helper function for get_permissions() and change_permissions().

    Returns the integer containing the file mode permissions for the
    given pathname.
    """
    import stat
    return stat.S_IMODE( os.stat(path)[stat.ST_MODE] )


def get_owner_bits():
    """
    Helper function for get_permissions() and change_permissions().
    
    Returns a pair, the mask for the owner bits (an int), and a dict mapping
    strings to bits (integers).
    """
    import stat
    
    owner_mask = (stat.S_ISUID|stat.S_IRWXU)
    
    owner_bits = {
            'r' : stat.S_IRUSR,
            'w' : stat.S_IWUSR,
            'x' : stat.S_IXUSR,
            's' : stat.S_IXUSR|stat.S_ISUID,
            'rw' : stat.S_IRUSR|stat.S_IWUSR,
            'rx' : stat.S_IRUSR|stat.S_IXUSR,
            'rs' : stat.S_IRUSR|stat.S_IXUSR|stat.S_ISUID,
            'wx' : stat.S_IWUSR|stat.S_IXUSR,
            'ws' : stat.S_IWUSR|stat.S_IXUSR|stat.S_ISUID,
            'rwx' : stat.S_IRWXU,
            'rws' : stat.S_IRWXU|stat.S_ISUID,
        }
    owner_bits['---'] = 0
    owner_bits['r--'] = owner_bits['r']
    owner_bits['-w-'] = owner_bits['w']
    owner_bits['--x'] = owner_bits['x']
    owner_bits['--s'] = owner_bits['s']
    owner_bits['rw-'] = owner_bits['rw']
    owner_bits['r-x'] = owner_bits['rx']
    owner_bits['r-s'] = owner_bits['rs']
    owner_bits['-wx'] = owner_bits['wx']
    owner_bits['-ws'] = owner_bits['ws']

    return owner_mask, owner_bits


def get_group_bits():
    """
    Helper function for get_permissions() and change_permissions().
    Same as get_owner_bits() except for group.
    """
    import stat

    group_mask = (stat.S_ISGID|stat.S_IRWXG)
    
    group_bits = {
            'r' : stat.S_IRGRP,
            'w' : stat.S_IWGRP,
            'x' : stat.S_IXGRP,
            's' : stat.S_IXGRP|stat.S_ISGID,
            'rw' : stat.S_IRGRP|stat.S_IWGRP,
            'rx' : stat.S_IRGRP|stat.S_IXGRP,
            'rs' : stat.S_IRGRP|stat.S_IXGRP|stat.S_ISGID,
            'wx' : stat.S_IWGRP|stat.S_IXGRP,
            'ws' : stat.S_IWGRP|stat.S_IXGRP|stat.S_ISGID,
            'rwx' : stat.S_IRWXG,
            'rws' : stat.S_IRWXG|stat.S_ISGID,
        }
    group_bits['---'] = 0
    group_bits['r--'] = group_bits['r']
    group_bits['-w-'] = group_bits['w']
    group_bits['--x'] = group_bits['x']
    group_bits['--s'] = group_bits['s']
    group_bits['rw-'] = group_bits['rw']
    group_bits['r-x'] = group_bits['rx']
    group_bits['r-s'] = group_bits['rs']
    group_bits['-wx'] = group_bits['wx']
    group_bits['-ws'] = group_bits['ws']

    return group_mask, group_bits


def get_world_bits():
    """
    Helper function for get_permissions() and change_permissions().
    Same as get_owner_bits() except for group.
    """
    import stat

    world_mask = stat.S_IRWXO
    
    world_bits = {
            'r' : stat.S_IROTH,
            'w' : stat.S_IWOTH,
            'x' : stat.S_IXOTH,
            'rw' : stat.S_IROTH|stat.S_IWOTH,
            'rx' : stat.S_IROTH|stat.S_IXOTH,
            'wx' : stat.S_IWOTH|stat.S_IXOTH,
            'rwx' : stat.S_IRWXO,
        }
    world_bits['---'] = 0
    world_bits['r--'] = world_bits['r']
    world_bits['-w-'] = world_bits['w']
    world_bits['--x'] = world_bits['x']
    world_bits['rw-'] = world_bits['rw']
    world_bits['r-x'] = world_bits['rx']
    world_bits['-wx'] = world_bits['wx']

    return world_mask, world_bits


def change_filemode( fmode, spec, *more_specs ):
    """
    Helper function for get_permissions() and change_permissions().

    Modifies the given file mode (an int) according to one or more
    specifications.  A specification is a string with format

        {u|g|o}{=|+|-}{one two or three letter sequence}

    where

        the first character: u=user/owner, g=group, o=other/world
        the second character: '=' means set, '+' means add, '-' means remove
        the permission characters: r=read, w=write, x=execute, s=sticky

    For example, "u+x" means add user execute permission, and "g=rx" means
    set the group permissions to exactly read, no write, execute.

    Returns the file mode as modified by the specifications (an int).
    """
    for s in (spec,)+more_specs:
        assert len(s) >= 3
        who = s[0] ; assert who in 'ugo'
        op = s[1] ; assert op in '=+-'
        what = s[2:]
        if who == 'u':
            owner_mask, owner_bits = get_owner_bits()
            mask = owner_mask
            bits = owner_bits[what]
        elif who == 'g':
            group_mask, group_bits = get_group_bits()
            mask = group_mask
            bits = group_bits[what]
        else:
            world_mask, world_bits = get_world_bits()
            mask = world_mask
            bits = world_bits[what]

        if op == '=':   fmode = ( fmode & (~mask) ) | bits
        elif op == '+': fmode = fmode | bits
        else:           fmode = fmode & ( ~(bits) )

    return fmode


############################################################################

def move_aside_existing_path( path, keep=1 ):
    """
    Renames a path to one with '.old0' appended.  By default, only one old
    path is kept (older ones are deleted).
    """
    if os.path.exists( path ):

        pat = re.compile( '[.]old[0-9]+$' )

        fL = []

        for f in glob.glob( os.path.abspath(path)+'.old*' ):
            ext = os.path.splitext(f)[1]
            if pat.search( ext ) != None:
                num = int( ext[4:] )
                if num+1 < keep:
                    fL.append( (num,f) )
                else:
                    fault_tolerant_remove( f )

        fL.sort()
        fL.reverse()

        for num,f in fL:
            bn,ext = os.path.splitext(f)
            os.rename( f, bn+'.old'+str(num+1) )

        if keep > 0:
            os.rename( path, path+'.old0' )


def fault_tolerant_remove( path, num_attempts=5 ):
    ""
    import libvvtest.pathutil as pathutil
    return pathutil.fault_tolerant_remove( path, num_attempts )
