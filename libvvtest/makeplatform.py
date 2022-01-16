#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import sys
import os
from os.path import join as pjoin, normpath, abspath, basename
import platform

from .vvplatform import Platform
from .importutil import import_file_from_sys_path, gather_modules_from_filename


platform_attrs = [
    [ 'batchsys', str, 'batch_system',
            'the batch system type, such as "slurm" or "lsf"' ],
    [ 'ppn', int, 'processors_per_node', 'cores_per_node',
            "num cores per compute node" ],
    [ 'dpn', int, 'devices_per_node',
            "num devices (eg, GPUs) per compute node" ],
    [ 'queue', str, 'q', 'partition',
            "the queue/partition to submit each batch job" ],
    [ 'account', str, 'PT',
            "give a string value to batch job submissions" ],
    [ 'variation', str,
            "a variation of a batch system (eg, knl or select)" ],
    [ 'walltime', str,
            "number of seconds to request for each batch job" ],
    [ 'maxprocs', int,
            "max processors per batch job, or num cores on the workstation" ],
    [ 'maxdevices', int,
            "max devices per batch job, or num devices on the workstation" ],
    [ 'maxqtime', int,
            "max time allowed for each batch job submission" ],
    [ 'maxsubs', int,
            "maximum concurrent submissions given to the batch queue" ],
    [ 'QoS', str,
            '"Quality of Service" e.g. "normal", "long", etc.' ],
    [ 'testingdir', str,
            "(under development)" ],
    [ 'extra_flags', str, 'submit_flags',
            "arbitrary command line options passed to the batch submit command" ],
]


class AttrParser:

    def __init__(self, attr_table=platform_attrs):
        ""
        self.tab = attr_table
        self.known = set( [ L[0] for L in attr_table ] )

    def parse_in_place(self, attrs):
        """
        Modifies the given attributes dictionary:
            1. replaces aliases with their primary names
            2. removes aliases from the dictionary
            3. if more than one name is given, checks for consistency
            4. raises exception for unknown attribute names
        """
        for spec in self.tab:

            name = spec[0]
            valtype = spec[1]
            aliases = spec[2:-1]

            vals = self._collect_values( attrs, valtype, name, *aliases )

            if len( vals ) > 0:
                if not self._consistent_values( vals ):
                    raise Exception( 'values for attribute '+repr(name) + \
                        ' are not consistent: '+str(vals) )

                attrs[name] = vals[0]
                for alias in aliases:
                    attrs.pop( alias, None )

        for name,val in attrs.items():
            if name not in self.known:
                raise Exception( 'unknown attribute name: '+repr(name) )

        return attrs

    def _collect_values(self, attrs, valtype, *names):
        ""
        vals = []
        for key in names:
            val = self._get_value( attrs, key, valtype )
            if val is not None:
                vals.append( val )
        return vals

    def _get_value(self, attrs, name, valtype):
        ""
        if name in attrs:
            try:
                val = valtype( attrs[name] )
            except Exception as e:
                raise Exception( 'could not cast attribute name '+repr(name) + \
                    ' to '+str(valtype)+': '+str(e) )
            return val
        else:
            return None

    def _consistent_values(self, values):
        ""
        if len( set( values ) ) > 1:
            return False
        else:
            return True


def create_Platform_instance( platname, mode, platopts,
                              numprocs, maxprocs, devices, max_devices,
                              onopts, offopts ):
    """
    The name=value options given to the Platform object originate from these
    places:

        (1) direct from command line, such as -N and --max-devices
        (2) indirect from command line, --platopts name=value
        (3) options given to setBatchSystem() in platform_plugin.py
        (4) set via platcfg.setattr() in platform_plugin.py
    """
    assert mode in ['direct','batch','batchjob']

    apsr = AttrParser()

    apsr.parse_in_place( platopts )

    optdict = {}
    if platname: optdict['--plat']    = platname
    if platopts: optdict['--platopt'] = platopts
    if onopts:   optdict['-o']        = onopts
    if offopts:  optdict['-O']        = offopts

    platname,cplrname = determine_platform_and_compiler( platname, onopts, offopts )

    # options (2) are available to platform plugin through the 'optdict' (yuck!)
    platcfg = PlatformConfig( apsr, optdict, platname, cplrname )

    # platform plugin can set attrs via:
    #   - options (3) by calling setBatchSystem()
    #   - options (4) by calling setattr() directly
    initialize_platform( platcfg )

    # options (2) are transferred/overwritten to the platconfig object attrs
    for n,v in platopts.items():
        platcfg.setattr( n, v )

    # the union of all options are given to Platform object
    plat = Platform( mode=mode,
                     platname=platname,
                     cplrname=cplrname,
                     environ=platcfg.envD,
                     attrs=platcfg.attrs )

    # options (1) are selected first in here if non-None
    plat.initialize( numprocs, maxprocs, devices, max_devices )

    return plat


class PlatformConfig:
    """
    This class is used as an interface to the platform_plugin.py mechanism.
    It is only necessary for backward compatibility, because a Platform
    object used to be passed into the plugin initialize() function. Using
    this "proxy" object allows the configuration mechanism to be separated
    from the implementation (the Platform class).
    """

    def __init__(self, attrpsr, optdict, platname, cplrname):
        ""
        self.attrpsr = attrpsr
        self.optdict = optdict
        self.platname = platname
        self.cplrname = cplrname

        self.envD = {}
        self.attrs = {}

    def getName(self):  return self.platname
    def getCompiler(self): return self.cplrname
    def getOptions(self): return self.optdict

    def setenv(self, name, value):
        ""
        if value == None:
            if name in self.envD:
                del self.envD[name]
        else:
            self.envD[name] = value

    def setattr(self, name, value):
        ""
        if value == None:
            if name in self.attrs:
                del self.attrs[name]
        else:
            self.attrs[name] = value
            self.attrpsr.parse_in_place( self.attrs )

    def getattr(self, name, *default):
        ""
        if len(default) > 0:
            return self.attrs.get( name, default[0] )
        else:
            return self.attrs[name]

    def setBatchSystem(self, batchsys, ppnarg, **kwargs ):
        ""
        self.attrpsr.parse_in_place( kwargs )

        ppn = kwargs.get( 'ppn', ppnarg )
        assert ppn and ppn > 0

        self.setattr( 'batchsys', batchsys )

        for n,v in kwargs.items():
            self.setattr( n, v )

        if 'ppn' not in self.attrs:
            self.setattr( 'ppn', ppn )

        self.attrpsr.parse_in_place( self.attrs )


def determine_platform_and_compiler( platname, onopts, offopts ):
    ""
    optdict = { '-o':onopts, '-O':offopts }
    if platname: optdict['--plat'] = platname

    modlist = gather_modules_from_filename( 'idplatform.py' )

    if not platname:
        for idmod in modlist:
            if hasattr( idmod, 'platform' ):
                # TODO: use of platform() was deprecated Jan 2022
                platname = idmod.platform( optdict )
                break
            elif hasattr( idmod, 'get_platform' ):
                pname = idmod.get_platform()
                if pname:
                    platname = pname
                    break

    if not platname:
        platname = platform.uname()[0]

    cplrname = None

    for idmod in modlist:
        if hasattr( idmod, 'compiler' ):
            # TODO: use of compiler() was deprecated Jan 2022
            cname = idmod.compiler( platname, optdict )
            if cname:
                cplrname = cname
            break
        elif hasattr( idmod, 'get_compiler' ):
            cname = idmod.get_compiler( platname, onopts )
            if cname:
                cplrname = cname
                break

    return platname, cplrname


def initialize_platform( platcfg ):
    ""
    plug = import_file_from_sys_path( 'platform_plugin.py' )

    if plug is not None and hasattr( plug, 'initialize' ):
        plug.initialize( platcfg )
