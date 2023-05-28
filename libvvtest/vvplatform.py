#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys
import platform

from . import rpool
from . import rprobe
from . import logger


class Platform:

    def __init__(self, mode='direct',
                       platname=platform.uname()[0],
                       cplrname=None,
                       environ={},
                       attrs={} ):
        ""
        self.mode = mode
        self.platname = platname
        self.cplrname = cplrname

        self.attrs = dict( attrs )

        self.maxsize  = (None,None)  # max core, max device
        self.size     = (None,None)  # num core, num device
        self.nodesize = (None,None)  # ppn, dpn

        self.procpool = None
        self.devicepool = None

    # ----------------------------------------------------------------

    def getName(self):  return self.platname
    def getCompiler(self): return self.cplrname

    def getMaxSize(self):
        ""
        return self.maxsize

    def getSize(self):
        ""
        return self.size

    def getNodeSize(self):
        ""
        return self.nodesize

    def getAttributes(self):
        ""
        return self.attrs

    def display(self):
        ""
        s = "Platform " + self.platname
        if self.mode == 'batch':
            s += ', batchsys='+str(self.attrs.get('batchsys',None))
            s += ', ppn='+str(self.attrs.get('ppn',None))
        else:
            np,nd = self.getSize()
            maxnp,maxnd = self.getMaxSize()
            if np    is not None: s += ', num cores = '+str(np)
            if maxnp is not None: s += ', max cores = '+str(maxnp)
            if nd    is not None: s += ', num devices = '+str(nd)
            if maxnd is not None: s += ', max devices = '+str(maxnd)
        logger.info( s )

    ##################################################################

    def getattr(self, name, *default):
        ""
        if len(default) > 0:
            return self.attrs.get( name, default[0] )
        else:
            return self.attrs[name]

    def getDefaultBatchLimit(self):
        ""
        n = self.attrs.get( 'maxsubs', 5 )
        return n

    def initialize(self, num_procs, max_procs, num_devices, max_devices ):
        """
        Determine and set the number of CPU cores and devices.  The arguments
        are from the command line:

            num_procs   is -n
            num_devices is --devices
            max_procs   is -N
            max_devices is --max-devices
        """
        self._init_size( num_procs, max_procs, num_devices, max_devices )

        if self.mode != 'batch':
            self._construct_resource_pools()

        bsys = self.attrs.get( 'batchsys', None )
        if self.mode == 'batch' and (bsys is None or bsys == 'subprocs'):
            self._set_subprocess_batching()

        if self.mode == 'direct':
            self._set_workstation_node_size()
        else:
            self._set_batch_node_size()

    def _init_size(self, num_procs, max_procs, num_devices, max_devices):
        ""
        plugmax = self._get_max_size_from_plugin( 'maxprocs' )
        np,maxnp = self._select_size( num_procs, max_procs, plugmax,
                                      self._backup_max_procs )

        plugmax = self._get_max_size_from_plugin( 'maxdevices' )
        nd,maxnd = self._select_size( num_devices, max_devices, plugmax,
                                      self._backup_max_devices )

        self.size = (np,nd)
        self.maxsize = (maxnp,maxnd)

    def _get_max_size_from_plugin(self, attrname):
        ""
        if self.mode == 'batchjob':
            # don't use the plugin value for batch jobs
            plugmax = None
        else:
            plugmax = self.attrs.get( attrname, None )

        return plugmax

    def _select_size(self, cmd_num, cmd_max, plugin_max, backup):
        ""
        mx = cmd_max
        if mx is None:
            mx = plugin_max
            if mx is None:
                mx = backup( cmd_num )

        num = cmd_num
        if num is None and mx:
            num = mx

        return num,mx

    def _backup_max_procs(self, num_procs):
        ""
        if self.mode == 'direct':
            ppn = self.attrs.get( 'ppn', None )
            if ppn:
                return ppn
            else:
                return rprobe.probe_num_processors( 4 )
        else:
            return None

    def _backup_max_devices(self, num_devices):
        ""
        dpn = self.attrs.get( 'dpn', None )

        if self.mode == 'direct':
            if dpn:
                return dpn
            elif num_devices is None:
                return 0
            else:
                return num_devices
        elif self.mode == 'batch':
            if dpn and dpn > 0:
                return None
            else:
                return 0
        else:
            return None

    def _set_batch_node_size(self):
        ""
        if 'ppn' not in self.attrs or self.attrs['ppn'] <= 0:
            raise Exception( 'batch mode requested, but "cores_per_node" '
                             'not set on the command line or in the plugin' )

        self.nodesize = ( self.attrs['ppn'], self.attrs.get('dpn',None) )

    def _set_workstation_node_size(self):
        ""
        maxnp,maxnd = self.maxsize

        ppn = self.attrs.get( 'ppn', None )
        if not ppn:
            ppn = maxnp or None

        dpn = self.attrs.get( 'dpn', None )
        if not dpn:
            dpn = maxnd or None

        self.nodesize = ( ppn, dpn )

    def _construct_resource_pools(self):
        ""
        np,nd = self.size
        maxnp,maxnd = self.maxsize

        if np:
            self.procpool = rpool.ResourcePool( np, maxnp )

        if nd:
            self.devicepool = rpool.ResourcePool( nd, maxnd )

    def _set_subprocess_batching(self):
        """
        If cores/devices per node is not set, we set the compute node size
        to the size of the workstation. This is an arbitrary choice, but
        makes sense for the "nnode" parameterization.
        """
        self.attrs['batchsys'] = 'subprocs'

        maxnp,maxnd = self.maxsize
        if not maxnp:
            maxnp = rprobe.probe_num_processors( 4 )

        self.attrs['ppn'] = self.attrs.get( 'ppn', maxnp )
        self.attrs['dpn'] = self.attrs.get( 'dpn', maxnd )

    def sizeAvailable(self):
        ""
        sznp = self.procpool.numAvailable()
        if self.devicepool is None:
            return ( sznp, 0 )
        else:
            return ( sznp, self.devicepool.numAvailable() )

    def getResources(self, size):
        ""
        np,ndevice = size

        procs = self.procpool.get( np )

        if self.devicepool == None or ndevice == None:
            devices = None
        else:
            devices = self.devicepool.get( max( 0, int(ndevice) ) )

        job_info = construct_job_info( procs, self.procpool,
                                       devices, self.devicepool,
                                       self.getattr( 'mpifile', '' ),
                                       self.getattr( 'mpiopts', '' ) )

        return job_info

    def returnResources(self, job_info):
        ""
        self.procpool.put( job_info.procs )
        if self.devicepool != None and job_info.devices != None:
            self.devicepool.put( job_info.devices )

    # ----------------------------------------------------------------

    def testingDirectory(self):
        """
        """
        if 'TESTING_DIRECTORY' in os.environ:
            return os.environ['TESTING_DIRECTORY']

        elif 'testingdir' in self.attrs:
            return self.attrs['testingdir']

        return None


def determine_processor_cores( num_procs, max_procs, plugin_max, use_probe=True ):
    ""
    if max_procs is None:
        if plugin_max is None and use_probe:
            mx = rprobe.probe_num_processors( 4 )
        else:
            mx = plugin_max
    else:
        mx = max_procs

    if num_procs is None:
        np = mx
    else:
        np = num_procs

    return np,mx


def determine_device_count( num_devices, max_devices, plugin_max ):
    ""
    if max_devices is None:
        mx = plugin_max
    else:
        mx = max_devices

    if num_devices is None:
        nd = mx
    else:
        nd = num_devices

    return nd,mx


##########################################################################

class JobInfo:
    """
    This object is used to communicate and hold information for a job
    processor request, including a string to give to the mpirun command, if
    any.  It is returned to the Platform when the job finishes.
    """
    def __init__(self, procs, maxprocs):
        ""
        self.procs = procs
        self.maxprocs = maxprocs
        self.devices = None
        self.maxdevices = None
        self.mpi_opts = ''


def construct_job_info( procs, procpool,
                        devices, devicepool,
                        mpifile, mpiopts ):
    ""
    numprocs = procpool.numTotal()
    maxprocs = procpool.maxAvailable()

    job_info = JobInfo( procs, maxprocs )

    if devices is not None:
        job_info.devices = devices
        job_info.maxdevices = devicepool.maxAvailable()

    if mpifile == 'hostfile':
        # use OpenMPI style machine file
        job_info.mpi_opts = "--hostfile machinefile"
        slots = min( len(procs), numprocs )
        job_info.machinefile = \
                    platform.uname()[1].strip() + " slots=" + str(slots) + '\n'

    elif mpifile == 'machinefile':
        # use MPICH style machine file
        job_info.mpi_opts = "-machinefile machinefile"
        job_info.machinefile = ''
        for i in range(len(procs)):
            job_info.machinefile += machine + '\n'

    if mpiopts:
        job_info.mpi_opts += ' ' + mpiopts

    return job_info
