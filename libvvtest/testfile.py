#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os
from os.path import basename

from .paramset import ParameterSet


class TestFile:

    def __init__(self, rootpath, filepath):
        ""
        assert not os.path.isabs(filepath)

        self.rootpath = rootpath
        self.filepath = filepath

        self.specform = None       # None means construction not done,
                                   # or 'xml' or 'script'

        self.enabled = True
        self.plat_enable = None    # a WordExpression
        self.option_enable = None  # a WordExpression
        self.keywords = set()      # set of strings
        self.paramset = ParameterSet()
        self.param_types = {}      # param name to param type
        self.analyze_spec = None
        self.timeout = None        # timeout value in seconds (an integer)
        self.preload = None        # a string label
        self.execL = []            # list of
                                   #   (name, fragment, exit status, analyze)
                                   # where name is None when the
                                   # fragment is a raw fragment, exit status
                                   # is any string, and analyze is true/false
        self.lnfiles = []          # list of (src name, test name)
        self.cpfiles = []          # list of (src name, test name)
        self.baseline_files = []   # list of (test name, src name)
        self.baseline_spec = None
        self.src_files = []        # extra source files listed by the test
        self.deps = []             # list of DependencyPattern
        self.skip_reason = None

    def getFilename(self):
        """
        The full path of the original test specification file.
        """
        return os.path.join( self.rootpath, self.filepath )

    def getRootpath(self):
        """
        The top directory of the original scan.
        """
        return self.rootpath

    def getFilepath(self):
        """
        The original test specification file relative to the root path.
        """
        return self.filepath

    def getDirectory(self):
        """
        The directory containing the original test specification file.
        """
        return os.path.dirname( self.getFilename() )

    def isEnabled(self):
        ""
        return self.enabled

    def setEnabled(self, is_enabled):
        ""
        if is_enabled:
            self.enabled = True
        else:
            self.enabled = False

    def setSkipped(self, reason):
        ""
        self.skip_reason = reason

    def setEnablePlatformExpression(self, word_expression):
        ""
        self.plat_enable = word_expression

    def getPlatformEnableExpression(self):
        ""
        return self.plat_enable

    def setEnableOptionExpression(self, word_expression):
        ""
        self.option_enable = word_expression

    def getOptionEnableExpression(self):
        ""
        return self.option_enable

    def setKeywordList(self, keyword_list):
        """
        A list of strings.
        """
        self.keywords = set( keyword_list )

    def getKeywordList(self, include_implicit=True):
        """
        Returns the list of keyword strings.  If 'include_implicit' is True,
        the list includes the test name and more.
        """
        kwset = set( self.keywords )

        if include_implicit:
            kwset.add( os.path.splitext( basename( self.filepath ) )[0] )

            for n,s,x,b in self.execL:
                if n:
                    kwset.add( n )

        return list( kwset )

    def getParameterTypes(self):
        ""
        return self.paramset.getParameterTypeMap()

    def setParameterSet(self, pset):
        ""
        self.paramset = pset

    def getParameterSet(self):
        """
        Return the test's ParameterSet instance, which maps parameter names
        to a list of parameter values.
        """
        return self.paramset

    def setAnalyzeScript(self, script_spec):
        ""
        self.analyze_spec = script_spec

    def getAnalyzeScript(self):
        """
        Returns None, or a string if this is an analyze test.  The string is
        is one of the following:

            1. If this test is specified with XML, then the returned string
               is a csh script fragment.

            2. If this is a script test, and the returned string starts with
               a hyphen, then the test script should be run with the string
               as an option to the base script file.

            3. If this is a script test, and the returned string does not start
               with a hyphen, then the string is a filename of a separate
               script to run.  The filename is a relative path to
               getDirectory().
        """
        return self.analyze_spec

    def setTimeout(self, timeout):
        """
        Adds a timeout specification.  Sending in None will remove the timeout.
        """
        if timeout != None:
            timeout = int(timeout)
        self.timeout = timeout

    def getTimeout(self):
        """
        Returns a timeout specification, in seconds (an integer).  Or None if
        not specified.
        """
        return self.timeout

    def setPreloadLabel(self, label):
        ""
        self.preload = label

    def getPreloadLabel(self):
        ""
        return self.preload

    def appendExecutionFragment(self, fragment, exit_status, analyze):
        """
        Append a raw execution fragment to this test.  The exit_status is any
        string.  The 'analyze' is either "yes" or "no".
        """
        self.execL.append( (None, fragment, exit_status, analyze) )
    
    def appendNamedExecutionFragment(self, name, content, exit_status):
        """
        Append an execution fragment to this test.  The name will be searched
        in a fragment database when writing the actual script.  The content
        replaces the $(CONTENT) variable in the database fragment.  The
        'exit_status' is any string.
        """
        assert name
        s = ' '.join( content.split() )  # remove embedded newlines
        self.execL.append( (name, s, exit_status, False) )

    def getExecutionList(self):
        """
        Returns, in order, raw fragments and named execution fragments for
        the given platform.  Returns a list of tuples
          ( name, fragment, exit status, analyze boolean )
        where 'name' is None for raw fragments and 'exit status' is a string.
        """
        return [] + self.execL
   
    def addLinkFile(self, srcname, destname=None):
        """
        Add the given file name to the set of files to link from the test
        source area into the test execution directory.  The 'srcname' is an
        existing file, and 'destname' is the name of the sym link file in
        the test execution directory.  If 'destname' is None, the base name
        of 'srcname' is used.
        """
        assert srcname and srcname.strip()
        if (srcname,destname) not in self.lnfiles:
            self.lnfiles.append( (srcname,destname) )
    
    def getLinkFileList(self):
        """
        Returns a list of pairs (source filename, test filename) for files
        that are to be soft linked into the testing directory.  The test
        filename may be None if it was not specified (meaning the name should
        be the same as the name in the source directory).
        """
        return list( self.lnfiles )

    def addCopyFile(self, srcname, destname=None):
        """
        Add the given file name to the set of files to copy from the test
        source area into the test execution directory.  The 'srcname' is an
        existing file, and 'destname' is the name of the file in the test
        execution directory.  If 'destname' is None, the base name of
        'srcname' is used.
        """
        assert srcname and not os.path.isabs( srcname )
        if (srcname,destname) not in self.cpfiles:
            self.cpfiles.append( (srcname,destname) )
    
    def getCopyFileList(self):
        """
        Returns a list of pairs (source filename, test filename) for files
        that are to be copied into the testing directory.  The test
        filename may be None if it was not specified (meaning the name should
        be the same as the name in the source directory).
        """
        return [] + self.cpfiles
    
    def addBaselineFile(self, test_dir_name, source_dir_name):
        """
        Add a file to be copied from the test directory to the source
        directory during baselining.
        """
        assert test_dir_name and source_dir_name
        self.baseline_files.append( (test_dir_name, source_dir_name) )

    def hasBaseline(self):
        """
        Returns true if this test has a baseline specification.
        """
        return len(self.baseline_files) > 0 or self.baseline_spec

    def getBaselineFiles(self):
        """
        Returns a list of pairs (test directory name, source directory name)
        of files to be copied from the testing directory to the source
        directory.
        """
        return self.baseline_files

    def setBaselineScript(self, script_spec):
        ""
        self.baseline_spec = script_spec

    def getBaselineScript(self):
        """
        Returns None if this test has no baseline script, or a string which
        is one of the following:

            1. If this test is specified with XML, then the returned string
               is a csh script fragment.

            2. If this is a script test, and the returned string starts with
               a hyphen, then the test script should be run with the string
               as an option to the base script file.

            3. If this is a script test, and the returned string does not start
               with a hyphen, then the string is a filename of a separate
               script to run.  The file path is relative to getDirectory().
        """
        return self.baseline_spec

    def setSourceFiles(self, files):
        """
        A list of file names needed by this test to run.
        """
        self.src_files = list( files )
    
    def getSourceFileList(self):
        ""
        return list( self.src_files )

    def addDependencyPattern(self, dep):
        """
        The 'dep' must be a DependencyPattern object.
        """
        self.deps.append( dep )

    def getDependencyPatterns(self):
        """
        Returns a list of DependencyPattern objects.
        """
        return list( self.deps )

    def setSpecificationForm(self, form):
        ""
        self.specform = form

    def constructionCompleted(self):
        ""
        return self.specform != None

    def getSpecificationForm(self):
        """
        returns None if construction is not completed, otherwise 'xml' or 'script'
        """
        return self.specform
