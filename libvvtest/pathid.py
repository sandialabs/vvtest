#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys
from os.path import dirname, join as pjoin, basename


# the test root marker filename
VVTEST_ROOT_FILENAME = '.vvtest.txt'


class TestPathIdentification:
    """
    Note: The cache effectiveness could be improved by checking if the
          incoming path is a subdir of a path in the cache.  However, it
          may break if soft links are used in the test repository.
    """

    def __init__(self):
        ""
        self.cache = {}

    def get_testid(self, test_src_filename, testspec_id):
        """
        Creates a test ID comprised of a TestSpec ID with the filepath
        replaced with the pathid.  Returns None if the pathid could not be
        determined.
        """
        testid = None

        pathid = self.get_pathid( test_src_filename )
        if pathid is not None:
            tid = list( testspec_id )
            tid[0] = pathid
            testid = tuple( tid )

        return testid

    def get_pathid(self, test_src_filename):
        """
        """
        cache_d,bname = os.path.split( test_src_filename )

        if cache_d in self.cache:
            trail = self.cache[ cache_d ]
        else:
            d,b = os.path.split( os.path.realpath( test_src_filename ) )

            trail = get_path_list_by_vvtest_root(d)

            if trail is None:
                trail = get_path_list_by_git_or_svn_repo(d)

            # add to the cache even if identification fails
            self.cache[ cache_d ] = trail

        pathid = None
        if trail is not None:
            pathlist = trail + [bname]  # need to make a copy of trail here
            pathid = pjoin( *pathlist )

        return pathid


def get_path_list_by_vvtest_root( filedir ):
    """
    returns a list of path segments from the .git or .svn directory to the
    given 'filedir' directory
    """
    d = filedir
    prev_d = None
    trail = []

    while d and d != prev_d and d != '/':

        fn = pjoin(d,VVTEST_ROOT_FILENAME)
        if os.path.exists(fn):
            with open( fn, 'rt' ) as fp:
                for line in fp:
                    if parse_root_path( line, trail ):
                        break
            trail.reverse()
            return trail

        trail.append( basename(d) )
        prev_d = d
        d = dirname(d)

    return None


def parse_root_path( line, trail ):
    """
    parses 'line' for ROOTPATH=path and appends 'trail' with the path segments
    returns True if the ROOTPATH was found
    """
    L = line.strip().split('=',1)
    if len(L) == 2 and L[0].strip() == 'ROOTPATH':
        d = L[1].strip()
        if d and not os.path.isabs(d):
            while d:
                d,seg = os.path.split(d)
                trail.append(seg)
            return True
    return False


def get_path_list_by_git_or_svn_repo( filedir ):
    """
    returns a list of path segments from the .git or .svn directory to the
    given 'filedir' directory
    """
    d = filedir
    prev_d = None
    trail = []

    while d and d != prev_d and d != '/':

        if os.path.exists(pjoin(d,'.git')) or os.path.exists(pjoin(d,'.svn')):
            trail.reverse()
            return trail

        trail.append( basename(d) )
        prev_d = d
        d = dirname(d)

    return None
