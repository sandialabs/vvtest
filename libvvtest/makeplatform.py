#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import sys
import os
import shlex
from os.path import join as pjoin, normpath, abspath, basename
import platform

from .vvplatform import Platform
from .importutil import import_file_from_sys_path, gather_modules_by_filename


def list_like(arg):
    if isinstance(arg, str):
        return shlex.split(arg)
    return list(arg)


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
    [ 'submit_flags', list_like, 'extra_flags',
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
    ""
    assert mode in ['direct','batch','batchjob']

    attrtab = AttrTable()
    creator = PlatformCreator()

    platname,cplrname = creator.determine_platform_and_compiler( platname )

    if not creator.found_deprecated_plugin():

        specs = PlatformSpecs( attrtab )

        specs.add_group( platopts )
        specs.add_group( environ_platform_specs() )

        creator.load( specs )

        plat = Platform( mode=mode,
                         platname=platname,
                         cplrname=cplrname,
                         environ={},
                         attrs=dict(specs) )

    else:
        # TODO: this branch is deprecated and should be removed after Feb 2023

        # The name=value options given to the Platform object originate from these
        # places:
        #     (1) direct from command line, such as -N and --max-devices
        #     (2) indirect from command line, --platopts name=value
        #     (2.1) settings from VVTEST_PLATFORM_SPECS environ variable
        #     (3) options given to setBatchSystem() in platform_plugin.py
        #     (4) set via platcfg.setattr() in platform_plugin.py

        platopts = attrtab.normalize_group( platopts )

        tmp = attrtab.normalize_group( environ_platform_specs() )
        tmp.update( platopts )
        platopts = tmp

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
        if creator.platplugin is not None and \
           hasattr( creator.platplugin, 'initialize' ):
            creator.platplugin.initialize( platcfg )

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


class PlatformCreator:

    def __init__(self):
        ""
        self.sizes = ( None, None, None, None )  # num procs, max procs, num gpus, max gpus
        self.platopts = {}
        self.options = ( [], [] )  # onopts, offopts

        self.idmods = gather_modules_by_filename( 'idplatform.py' )

        # TODO: this plugin is deprecated as of Feb 2022
        self.platplugin = import_file_from_sys_path( 'platform_plugin.py' )

        self.platname = None
        self.cplrname = None

    def set_command_line_sizes(self, num_procs, max_procs, num_devices, max_devices):
        ""
        self.sizes = ( num_procs, max_procs, num_devices, max_devices )

    def set_command_line_options(self, onopts, offopts):
        ""
        self.options = ( onopts, offopts )

    def set_command_line_platform_options(self, platopts):
        ""
        self.platopts = dict( platopts )

    def determine_platform_and_compiler(self, cmdline_platname):
        ""
        optdict = { '-o':self.options[0], '-O':self.options[1] }
        if cmdline_platname: optdict['--plat'] = cmdline_platname

        pname = None

        if cmdline_platname:
            pname = cmdline_platname
        elif 'VVTEST_PLATFORM' in os.environ:
            pname = os.environ['VVTEST_PLATFORM'].strip()
            if not pname:
                raise Exception( 'the VVTEST_PLATFORM environment '
                                 'variable cannot be empty' )
        else:
            for idmod in self.idmods:
                if hasattr( idmod, 'platform' ):
                    # TODO: use of platform() was deprecated Feb 2022
                    pname = idmod.platform( optdict )
                    break
                elif hasattr( idmod, 'get_platform' ):
                    plat = idmod.get_platform()
                    if plat:
                        pname = plat
                        break

            if not pname:
                pname = platform.uname()[0]

        cname = None

        for idmod in self.idmods:
            if hasattr( idmod, 'compiler' ):
                # TODO: use of compiler() was deprecated Feb 2022
                cplr = idmod.compiler( pname, optdict )
                if cplr:
                    cname = cplr
                break
            elif hasattr( idmod, 'get_compiler' ):
                cplr = idmod.get_compiler( pname, self.options[0] )
                if cplr:
                    cname = cplr
                    break

        self.platname = pname
        self.cplrname = cname

        return pname,cname

    def found_deprecated_plugin(self):
        ""
        return self.platplugin is not None

    def load(self, specs):
        ""
        for idmod in self.idmods:
            if hasattr( idmod, 'load_specifications' ):
                specs.set_unmodified()
                rtn = idmod.load_specifications( specs,
                                                 self.platname,
                                                 self.cplrname,
                                                 self.options[0] )
                if rtn != 'continue':
                    if rtn == 'break' or specs.is_modified():
                        break


def environ_platform_specs():
    """
    gets VVTEST_PLATFORM_SPECS from os.environ and parses the value into
    a dict; the format is comma separated name=value, for example:

        maxdevices=4,queue=long,batchsys=slurm
    """
    eD = {}
    if 'VVTEST_PLATFORM_SPECS' in os.environ:
        specstr = os.environ['VVTEST_PLATFORM_SPECS']
        for kvstr in specstr.strip().split(','):
            kvstr = kvstr.strip()
            if kvstr:
                kvL = [ item.strip() for item in kvstr.split('=',1) ]
                if len(kvL) != 2 or not kvL[0]:
                    raise Exception(
                        'invalid VVTEST_PLATFORM_SPECS syntax: '+repr(specstr) )
                eD[ kvL[0] ] = kvL[1]

    return eD


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

    def add_group(self, attrs):
        ""
        self.modified = True
        if self.attrtab is not None:
            attrs = self.attrtab.normalize_group( attrs )
        for k,v in attrs.items():
            if k not in self.specs:
                self.specs[k] = v

    def __len__(self):
        ""
        return len( self.specs )

    def __getitem__(self, key):
        ""
        key = self._normalize_key( key )
        return self.specs[key]

    def __contains__(self, key):
        ""
        key = self._normalize_key( key )
        return key in self.specs

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
