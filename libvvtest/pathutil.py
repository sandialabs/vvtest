#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys
import string
import random
import time
import shutil

from . import logger


def compute_relative_path(d1, d2):
    """
    Compute relative path from directory d1 to directory d2.
    """
    assert os.path.isabs(d1)
    assert os.path.isabs(d2)

    d1 = os.path.normpath(d1)
    d2 = os.path.normpath(d2)

    list1 = d1.split( os.sep )
    list2 = d2.split( os.sep )

    while True:
        try: list1.remove('')
        except Exception: break
    while True:
        try: list2.remove('')
        except Exception: break

    i = 0
    while i < len(list1) and i < len(list2):
        if list1[i] != list2[i]:
            break
        i = i + 1

    p = []
    j = i
    while j < len(list1):
        p.append('..')
        j = j + 1

    j = i
    while j < len(list2):
        p.append(list2[j])
        j = j + 1

    if len(p) > 0:
        return os.path.normpath( os.sep.join(p) )

    return "."


def relative_execute_directory( xdir, testdir, cwd ):
    """
    Returns the test execute directory relative to the given current working
    directory.
    """
    if testdir == None:
        return xdir

    d = os.path.join( testdir, xdir )
    sdir = is_subdir( cwd, d )
    if sdir == None or sdir == "":
        return os.path.basename( xdir )

    return sdir


def is_subdir( parent_dir, subdir ):
    """
    TODO: test for relative paths
    """
    lp = len(parent_dir)
    ls = len(subdir)
    if ls > lp and parent_dir + '/' == subdir[0:lp+1]:
        return subdir[lp+1:]
    return None


def remove_directory_contents( path ):
    ""
    logger.info( 'rm -rf', path+'/* ...', end='' )

    for f in os.listdir(path):
        df = os.path.join( path, f )
        fault_tolerant_remove( df )

    logger.info( 'done' )


def random_string( numchars=8 ):
    ""
    seq = string.ascii_letters + string.digits
    cL = [ random.choice( seq ) for _ in range(numchars) ]
    return ''.join( cL )


def fault_tolerant_remove( path, num_attempts=5 ):
    ""
    dn,fn = os.path.split( path )

    if fn.startswith( 'vvtest_remove_' ):
        rmpath = path
    else:
        rmpath = os.path.join( dn, 'vvtest_remove_'+random_string()+'_'+fn )
        try:
            os.rename( path, rmpath )
        except Exception as e:
            raise type(e)( 'Failed to remove path '+repr(path)+': '+str(e) )

    for i in range( num_attempts ):
        try:
            if os.path.islink( rmpath ):
                os.remove( rmpath )
            elif os.path.isdir( rmpath ):
                shutil.rmtree( rmpath )
            else:
                os.remove( rmpath )
            break
        except Exception:
            pass

        time.sleep(1)


class change_directory:
    """
    with change_directory( 'subdir' ):
        pass
    """

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
