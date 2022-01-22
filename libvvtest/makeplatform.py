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
            "max processors per batch job, or num cores on a workstation" ],
    [ 'maxdevices', int,
            "max devices per batch job, or num devices on a workstation" ],
    [ 'maxqtime', int,
            "max time allowed for each batch job submission" ],
    [ 'maxsubs', int,
            "maximum concurrent submissions given to the batch queue" ],
    [ 'QoS', str,
            '"Quality of Service" e.g. "normal", "long", etc.' ],
    [ 'testingdir', str,
            "(under development)" ],
    [ 'submit_flags', str, 'extra_flags',
            "arbitrary command line options passed to the batch submit command" ],
]


class AttrTable:

    def __init__(self, definitions=platform_attrs):
        ""
        self.names = {}  # maps aliases to primary name
        self.valtypes = {}  # maps primary name to value type

        for spec in definitions:
            name = spec[0]
            valtype = spec[1]
            aliases = spec[2:-1]

            self.valtypes[ name ] = valtype

            self.names[ name ] = name
            for alias in aliases:
                self.names[ alias ] = name

    def normalize(self, attrname, attrvalue):
        ""
        primary = self.normalize_name( attrname )
        value = self.normalize_value( attrvalue, primary, attrname )
        return primary,value

    def normalize_group(self, attrs):
        """
        Returns a new dictionary such that:
            1. Unknown attributes raise an exception
            2. Replaces aliases with their primary names
            3. Aliases are not included in the dictionary
            4. If more than one name/alias is given, the values must be equal
        """
        normed = {}

        for key,val in attrs.items():
            primary_name, attrvalue = self.normalize( key, val )
            self.check_consistency( primary_name, attrs )
            normed[primary_name] = attrvalue

        return normed

    def normalize_name(self, name):
        ""
        if name in self.names:
            return self.names[name]

        raise Exception( 'unknown attribute name: '+repr(name) )

    def normalize_value(self, value, primary_name, attrname):
        ""
        valtype = self.valtypes[ primary_name ]
        try:
            val = valtype( value )
        except Exception as e:
            raise Exception( 'could not convert attribute name ' + \
                repr(attrname) + ' to '+str(valtype)+': '+str(e) )
        return val

    def check_consistency(self, primary_name, attrgroup):
        ""
        nameset = set()
        valset = set()

        for alias,primary in self.names.items():
            if primary == primary_name:
                if alias in attrgroup:
                    nameset.add( alias )
                    val = self.normalize_value( attrgroup[alias], primary, alias )
                    valset.add( val )

        if len( set(valset) ) > 1:
            raise Exception( 'multiple values encountered for an attribute '
                'name plus aliases ('+', '.join([n for n in nameset])+') but '
                'those values are not the same: '+', '.join([v for v in valset]) )



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

    platname,cplrname = determine_platform_and_compiler( platname, onopts, offopts )

    attrtab = AttrTable()
    platopts = attrtab.normalize_group( platopts )

    optdict = {}
    if platname: optdict['--plat']    = platname
    if platopts: optdict['--platopt'] = platopts
    if onopts:   optdict['-o']        = onopts
    if offopts:  optdict['-O']        = offopts

    # options (2) are available to platform plugin through the 'optdict' (yuck!)
    platcfg = PlatformConfig( optdict, platname, cplrname )

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

    def __init__(self, optdict, platname, cplrname):
        ""
        self.optdict = optdict
        self.platname = platname
        self.cplrname = cplrname

        self.attrtable = AttrTable()
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
            n,v = self.attrtable.normalize( name, value )
            self.attrs[n] = v

    def getattr(self, name, *default):
        ""
        if len(default) > 0:
            return self.attrs.get( name, default[0] )
        else:
            return self.attrs[name]

    def setBatchSystem(self, batchsys, ppnarg, **kwargs ):
        ""
        batchattrs = self.attrtable.normalize_group( kwargs )

        ppn = batchattrs.get( 'ppn', ppnarg )
        assert ppn and ppn > 0

        self.setattr( 'batchsys', batchsys )

        for n,v in batchattrs.items():
            self.setattr( n, v )

        if 'ppn' not in self.attrs:
            self.setattr( 'ppn', ppn )

        self.attrs = self.attrtable.normalize_group( self.attrs )


class PlatformSpecs:

    def __init__(self, attrtab=None):
        ""
        self.attrtab = attrtab

        self.specs = {}
        self.modified = False

    def is_modified(self):
        ""
        return self.modified

    def set_unmodified(self):
        ""
        self.modified = False

    def __setitem__(self, key, value):
        """
        the assignment operator will not overwrite a key that already exists
        """
        key, value = self._normalize_item( key, value )
        self.modified = True
        if key not in self.specs:
            self.specs[key] = value

    def overwrite(self, key, value):
        """
        unlike the assignment operator, this function will overwrite a key
        """
        key, value = self._normalize_item( key, value )
        self.modified = True
        self.specs[key] = value

    def __len__(self):
        ""
        return len( self.specs )

    def __getitem__(self, key):
        ""
        key = self._normalize_key( key )
        return self.specs[key]

    def get(self, key, *default):
        ""
        key = self._normalize_key( key )
        if len(default) > 0:
            return self.specs.get( key, default[0] )
        else:
            return self.specs[key]

    def items(self): return self.specs.items()
    def keys(self): return self.specs.keys()
    def values(self): return self.specs.values()

    def _normalize_item(self, key, value):
        ""
        assert type(key) == type('')
        if self.attrtab is not None:
            return self.attrtab.normalize( key, value )
        return key,value

    def _normalize_key(self, key):
        ""
        assert type(key) == type('')
        if self.attrtab is not None:
            return self.attrtab.normalize_name( key )
        return key


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
