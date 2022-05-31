#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys
from os.path import dirname, normpath
from os.path import join as pjoin

import hashlib

DEFAULT_MAX_NAME_LENGTH = 100


class TestID:

    def __init__(self, testname, filepath, params, staged_names, idtraits={}):
        ""
        self.name = testname
        self.filepath = filepath
        self.params = params
        self.staged = staged_names
        self.idtraits = idtraits

    def computeExecuteDirectory(self):
        ""
        paramL = self._get_parameters( compress_stage=True, compress_hidden=True )
        return self._compute_execute_path( paramL )

    def computeDisplayString(self):
        ""
        paramL = self._get_parameters( compress_stage=True, compress_hidden=True )
        displ = self._compute_execute_path( paramL, shorten=False )
        displ += self._get_staging_suffix()

        return displ

    def computeID(self, compress_stage=False):
        ""
        lst = [ self.filepath, self.name ]
        lst.extend( self._get_parameters( compress_stage ) )
        return tuple( lst )

    def executeDirectoryIsShortened(self):
        ""
        paramL = self._get_parameters( compress_stage=True )
        xdir1 = self._compute_execute_path( paramL, shorten=True )
        xdir2 = self._compute_execute_path( paramL, shorten=False )

        return xdir1 != xdir2

    def computeMatchString(self):
        ""
        paramL = self._get_parameters( compress_stage=True, compress_hidden=False )
        displ = self._compute_execute_path( paramL, shorten=False )
        displ += self._get_staging_suffix()
        return displ

    def _get_parameters(self, compress_stage, compress_hidden=True):
        ""
        L = []
        if len( self.params ) > 0:
            for n,v in self.params.items():
                if self._hide_parameter( n, compress_stage, compress_hidden ):
                    pass
                elif self._compress_parameter( n, compress_stage ):
                    L.append( n )
                else:
                    L.append( n + '=' + v )
            L.sort()

            if len(L) == 0:
                # can only happen with minxdirs; it is a bit of a hack, but
                # a single empty string will result in an execute directory
                # that is distinguishable from an analyze test (it will have
                # a trailing dot)
                L.append('')

        return L

    def _compute_execute_path(self, paramlist, shorten=True):
        ""
        bname = self.name

        if len( paramlist ) > 0:
            bname += '.' + '.'.join(paramlist)

        if shorten:
            bname = self._compute_shortened_name( bname )

        path = normpath( pjoin( dirname( self.filepath ), bname ) )

        return path

    def _hide_parameter(self, param_name, compress_stage, compress_hidden):
        ""
        if compress_hidden and (param_name in self.idtraits.get('minxdirs',[])):
            return True
        elif compress_stage and self.staged:
            return param_name == self.staged[0]
        else:
            return False

    def _compress_parameter(self, param_name, compress_stage):
        ""
        if compress_stage and self.staged:
            if param_name in self.staged[1:]:
                return True
        return False

    def _compute_shortened_name(self, fullname):
        ""
        nchar = self.idtraits.get( 'numchars', DEFAULT_MAX_NAME_LENGTH )

        if nchar and len(fullname) > nchar:
            hsh = _compute_hash( fullname )[:10]
            return self.name[:20] + '.' + hsh
        else:
            return fullname

    def _get_staging_suffix(self):
        ""
        sfx = ''

        if self.staged:

            stage_name = self.staged[0]
            param_names = self.staged[1:]

            paramL = list( param_names )
            paramL.sort()
            pL = []
            for param in paramL:
                pL.append( param+'='+self.params[param] )

            sfx = ' ' + stage_name+'='+self.params[stage_name]
            sfx += '('+','.join( pL )+')'

        return sfx


if sys.version_info[0] < 3:
    def _compute_hash( astring ):
        ""
        return hashlib.sha1(astring).hexdigest()
else:
    def _compute_hash( astring ):
        ""
        return hashlib.sha1( astring.encode() ).hexdigest()
