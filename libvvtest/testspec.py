#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os
from os.path import basename

from .testfile import TestFile
from .testid import TestID


class TestSpec( TestFile ):
    """
    Holds the contents of a test specification in memory, including test
    realizations (instances) of the test.
    """

    def __init__(self, name, rootpath, filepath, idtraits={}):
        """
        A test object always needs a root path and file path, where the file
        path must be a relative path name.
        """
        TestFile.__init__( self, rootpath, filepath )

        self.name = name

        self.is_analyze = False

        self.params = {}           # name string to value string

        self.staged = None         # [ stage param name, param name, ... ]
        self.first_stage = True
        self.last_stage = True

        self.idtraits = idtraits
        self._set_identifiers()

    def getName(self):
        ""
        return self.name

    def getLinkFiles(self):
        ""
        lnf = self.getLinkFileList()

        srcfile = basename( self.getFilepath() )
        lnf.append( (srcfile,None) )

        if self.isAnalyze():
            analyze_spec = self.getAnalyzeScript()
            if analyze_spec and not analyze_spec.startswith('-'):
                lnf.append( (analyze_spec,None) )

        return lnf

    def getCopyFiles(self):
        ""
        return self.getCopyFileList()

    def getSourceFiles(self):
        """
        The files needed by this test that come from the source area. They
        include files to be copied, soft linked, rebaselined, and files just
        listed as needed.
        """
        S = set( self.getSourceFileList() )
        for f,tf in self.getLinkFiles(): S.add(f)
        for f,tf in self.getCopyFileList(): S.add(f)
        for tf,f in self.getBaselineFiles(): S.add(f)
        return list( S )

    def getExecuteDirectory(self):
        """
        The directory containing getFilepath() followed by a subdir containing
        the test name and the test parameters, such as "some/dir/myname.np=4".
        """
        return self.xdir

    def getDisplayString(self):
        """
        The execute directory plus staged information (if present).
        """
        return self.displ

    def getID(self):
        """
        A tuple uniquely identifying this test, which is composed of the
        test filename relative to the scan root, the test name, and the test
        parameters with values.
        """
        return self.testid

    def setStagedParameters(self, is_first_stage, is_last_stage,
                                  stage_name, *param_names):
        ""
        self.first_stage = is_first_stage
        self.last_stage = is_last_stage

        self.staged = [ stage_name ] + list( param_names )

        self._set_identifiers()

    def getStageID(self):
        ""
        if self.staged:
            stage_name = self.staged[0]
            stage_value = self.params[ stage_name ]
            return stage_name+'='+stage_value

        return None

    def getStageNames(self):
        ""
        return self.staged

    def isFirstStage(self):
        """
        True if this test is not staged or this is the first stage.
        """
        return self.first_stage

    def isLastStage(self):
        """
        True if this test is not staged or this is the last stage.
        """
        return self.last_stage

    def getLogFilename(self, baseline=False):
        """
        Usually 'execute.log' except for staged tests and when baselining.
        """
        stageid = self.getStageID()

        if baseline:
            fn = 'baseline.log'
        elif stageid != None:
            fn = 'execute_'+stageid+'.log'
        else:
            fn = 'execute.log'

        return fn

    def getKeywords(self, include_implicit=True):
        """
        Returns the list of keyword strings.  If 'include_implicit' is True,
        the parameter names and the test name itself is included in the list.
        """
        kwds = self.getKeywordList( include_implicit )

        if include_implicit:
            kwset = set( kwds )
            kwset.add( self.name )
            kwset.update( self.getParameterNames() )
            kwds = list( kwset )

        return kwds

    def hasKeyword(self, keyword):
        """
        Returns true if the keyword is contained in the list of keywords.
        """
        return keyword in self.getKeywords()

    def setParameters(self, param_dict):
        """
        Set the key/value pairs for this test and reset the ID and execute
        directory.
        """
        self.params = dict( param_dict )
        self._set_identifiers()

    def getParameters(self, typed=False):
        """
        Returns a dictionary mapping parameter names to values.  If 'typed'
        is True, the type map is applied to each value.
        """
        D = dict( self.params )

        if typed:
            apply_types_to_param_values( D, self.getParameterTypes() )

        return D

    def getParameterNames(self):
        """
        Returns a list of the parameter names for this test.
        """
        return self.params.keys()
    
    def getParameterValue(self, param_name):
        """
        Returns the string value for the given parameter name.
        """
        return self.params[param_name]

    def setIsAnalyze(self):
        ""
        self.is_analyze = True

    def isAnalyze(self):
        """
        Returns true if this is the analyze test of a parameterize/analyze
        test group.
        """
        return self.is_analyze

    def getTestID(self):
        """
        constructs and returns a TestID object; this object is used to
        determine the exec dir, the ID, and the display string
        """
        return TestID( self.name, self.getFilepath(),
                       self.params, self.staged,
                       self.idtraits )

    def getIDTraits(self):
        ""
        return self.idtraits

    def setIDTraits(self, idtraits):
        ""
        self.idtraits = idtraits
        self._set_identifiers()

    def _set_identifiers(self):
        ""
        tid = self.getTestID()

        self.testid = tid.computeID()
        self.xdir   = tid.computeExecuteDirectory()
        self.displ  = tid.computeDisplayString()


def apply_types_to_param_values( paramD, param_types ):
    ""
    for n,v in paramD.items():
        if n in param_types:
            paramD[n] = param_types[n](v)
