#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys
from os.path import normpath, dirname
from os.path import join as pjoin
import stat
import itertools

import perms
from .errors import FatalError
from . import pathutil


class PermissionSetter:
    
    def __init__(self, topdir, speclist):
        """
        The 'speclist' can be a list or a comma separate string, which is sent
        into the perms.py module for processing.  For example,

            wg-alegra,g=rX,o=
            [ 'wg-alegra', 'g=rX', 'o=' ]
            [ 'wg-alegra', 'g=rX,o=rX' ]
        """
        assert os.path.isabs( topdir )

        self.topdir = topdir
        self.specs = None
        self.cache = set()

        if speclist:
            self.specs = make_permission_specs( speclist )

    def apply(self, path):
        """
        If 'path' is a relative path, then it is assumed relative to 'topdir'.

        If 'path' is a subdirectory of 'topdir', then the permissions are set
        on the path and all intermediate directories at or below the 'topdir'.
        Otherwise, permissions are only set on the given 'path'.

        An instance of this class caches the paths that have had their
        permissions set and will not set them more than once.
        """
        if not self.specs:
            return

        if os.path.isabs( path ):

            assert os.path.exists( path ), 'path does not exist: '+repr(path)

            path = normpath( path )

            if not pathutil.is_subdir( self.topdir, path ):
                self.specs.apply( path )
                return

        else:
            path = normpath( path )
            assert not path.startswith( '..' )

            fp = normpath( pjoin( self.topdir, path ) )
            assert os.path.exists( fp ), 'path does not exist: '+repr(fp)

            path = fp

        while True:
            if path in self.cache:
                break

            self.specs.apply( path )
            self.cache.add( path )

            if os.path.samefile( path, self.topdir ):
                break

            up = dirname( path )
            if os.path.samefile( up, path ):
                break

            path = up

    def recurse(self, path):
        """
        If 'path' is a regular file, then permissions are applied to it.
        If 'path' is a directory, then permissions are applied recursively
        to the each entry in the directory.  Soft links are left untouched
        and not followed.
        """
        if not self.specs:
            return

        if not os.path.islink( path ):

            if os.path.isdir( path ):
                self.specs.apply( path, recurse=True )
            else:
                self.specs.apply( path )

    def set(self, path):
        """
        Apply permissions to the given path only.
        """
        if self.specs:
            self.specs.apply( path )


def make_permission_specs( speclist ):
    ""
    try:
        specs = perms.PermissionSpecifications( *speclist )
    except perms.PermissionSpecificationError as e:
        raise FatalError(
                'invalid permission specification or group name: ' + str(e) )

    return specs
