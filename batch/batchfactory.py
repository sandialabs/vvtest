#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.


def construct_batch_system( batchattrs ):
    ""
    qtype = batchattrs['batchsys']

    if qtype == 'subprocs':
        from . import subprocs
        batch = subprocs.SubProcs( **batchattrs )
    elif qtype == 'craypbs':
        from . import craypbs
        batch = craypbs.BatchCrayPBS( **batchattrs )
    elif qtype == 'pbs':
        from . import pbs
        batch = pbs.BatchPBS( **batchattrs )
    elif qtype == 'slurm':
        from . import slurm
        batch = slurm.BatchSLURM( **batchattrs )
    elif qtype == 'moab':
        from . import moab
        batch = moab.BatchMOAB( **batchattrs )
    elif qtype == 'lsf':
        from . import lsf
        batch = lsf.BatchLSF( **batchattrs )
    else:
        raise Exception( "Unknown batch system name: "+repr(qtype) )

    return batch
