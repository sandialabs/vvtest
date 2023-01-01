#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import os, sys
import time


# this is the file name of source tree runtimes files
runtimes_filename = "runtimes"

# this is the file name of the multiplatform runtimes file
multiruntimes_filename = "timings"


class TestResults:

    def __init__(self, results_filename=None):
        ""
        self.vers = 3
        self.hdr = {}

        # dataD maps test rootrel directory to testD
        #   testD maps test name to attrD
        #     attrD maps attribute name to attribute value
        self.dataD = {}

        # keeps a running min & max date of all tests
        self.daterange = None

        self.dcache = {}  # magic remove this

        if results_filename:
            self.readResults( results_filename )

    def platform  (self): return self.hdr.get('PLATFORM',None)
    def compiler  (self): return self.hdr.get('COMPILER',None)
    def machine   (self): return self.hdr.get('MACHINE',None)
    def testdir   (self): return self.hdr.get('TEST_DIRECTORY',None)
    def inProgress(self): return 'IN_PROGRESS' in self.hdr

    def addTest(self, testcase, rootrel):
        """
        Adds the test results for this test to the database.
        """
        tspec = testcase.getSpec()
        tstat = testcase.getStat()
        testkey = make_test_key( tspec )
        self.addTestName( rootrel, testkey, tstat.getAttrs() )

    def addTestName(self, rootrel, testkey, attrD):
        """
        The 'rootrel' is the test directory relative to the test root.  The
        'testkey' is the test name together with any parameter names and
        values.  If the test already exists, it is overwritten.
        """
        assert rootrel and rootrel != '.' and not os.path.isabs(rootrel)

        tD = self.dataD.get( rootrel, None )
        if tD == None:
            tD = {}
            self.dataD[rootrel] = tD
        aD = tD.get( testkey, None )
        if aD == None:
            aD = {}
            tD[testkey] = aD
        else:
            aD.clear()
        aD.update( attrD )

        self._accumulate_date_range( aD )

    def dirList(self):
        """
        Return a sorted list of root-relative directories stored in the
        database.
        """
        dL = list( self.dataD.keys() )
        dL.sort()
        return dL

    def testList(self, rootrel):
        """
        For a given root-relative directory, return a sorted list of test
        keys contained in that directory.
        """
        tD = self.dataD.get( rootrel, {} )
        tL = list( tD.keys() )
        tL.sort()
        return tL

    def testAttrs(self, rootrel, testkey):
        """
        For a given root-relative directory and a test key, return the test
        attribute dictionary.
        """
        tD = self.dataD.get( rootrel, {} )
        aD = tD.get( testkey, {} )
        return aD

    def getTime(self, rootrel, testkey):
        """
        Get the execution time of the given test.  If the test is not in the
        database, return None.
        """
        aD = self.testAttrs( rootrel, testkey )
        return aD.get( 'xtime', None )

    def dateRange(self):
        """
        Returns a pair (min date, max date) over all tests.  If there are no
        tests with a date defined, then this returns (None,None).
        """
        if self.daterange == None:
            return (None,None)
        return ( self.daterange[0], self.daterange[1] )

    def getCounts(self, tdd=False):
        """
        Counts the number of tests that pass, diff, fail, timeout, notrun,
        and unknown, and returns a tuple with the counts of each.  If 'tdd' is
        False, then tests marked TDD are excluded.  If 'tdd' is True, then
        only tests marked TDD are included.
        """
        np = nd = nf = nt = nr = unk = 0
        for d,tD in self.dataD.items():
            for tn,aD in tD.items():
                if ( tdd == False and 'TDD' not in aD ) or \
                   ( tdd == True and 'TDD' in aD ):
                    st = aD.get( 'state', '' )
                    if st == 'done':
                        rs = aD.get( 'result', '' )
                        if rs == 'pass': np += 1
                        elif rs == 'fail': nf += 1
                        elif rs == 'diff': nd += 1
                        elif rs == 'timeout': nt += 1
                        else: unk += 1
                    elif st == 'notrun': nr += 1
                    elif st == 'timeout': nt += 1
                    else: unk += 1
        return np,nd,nf,nt,nr,unk

    def getSummary(self):
        """
        Counts the number of tests that pass, fail, diff, timeout, etc, and
        returns a string with labels and the counts.
        """
        np, nd, nf, nt, nr, unk = self.getCounts()
        return 'pass='+str(np) + ' diff='+str(nd) + ' fail='+str(nf) + \
               ' timeout='+str(nt) + ' notrun='+str(nr) + ' ?='+str(unk)

    def collectResults(self, *args, **kwargs):
        """
        Collects all the test results into a dictionary mapping

            ( test directory, test name ) -> ( run date, result string )

        where the "run date" is zero if the test did not get run, and the
        "result string" is:

                state=<state>   : if the state matches one of the 'args'
                result=<result> : if the result matches one of the 'args'
                <empty string>  : if niether state nor result matches

        The dictionary is returned plus the number of tests that match the
        'args'.

        If 'matchlist=True' is given as a keyword argument, then the resulting
        dictionary will only contain test items if they match one of the 'args'.

        By default, tests marked TDD are ignored.  But if 'tdd=True' is given
        as a keyword argument, then only tests marked TDD are included.
        """
        getall = ( kwargs.get( 'matchlist', False ) == False )
        tdd = kwargs.get( 'tdd', False )

        nmatch = 0
        resD = {}
        for d,tD in self.dataD.items():
            for tn,aD in tD.items():

                if ( tdd and 'TDD' in aD ) or ( not tdd and 'TDD' not in aD ):
                    st = aD.get( 'state', '' )
                    rs = aD.get( 'result', '' )
                    if st in args:
                        res = 'state='+st
                        nmatch += 1
                    elif rs in args:
                        res = 'result='+rs
                        nmatch += 1
                    else:
                        res = ''

                    if getall or res:
                        xd = aD.get( 'xdate', 0 )
                        resD[ (d,tn) ] = ( xd, res )

        return resD,nmatch

    def writeResults(self, filename, plat_name, cplr_name,
                           mach_name, test_dir, inprogress=False):
        """
        Writes out test results for all tests, with a header that includes the
        directory in which the tests were run, the platform name, and the
        compiler name.
        """
        fp = open( filename, 'w' )

        fp.write( 'FILE_VERSION=results' + str(self.vers) + os.linesep )
        fp.write( 'PLATFORM=' + str(plat_name) + os.linesep )
        fp.write( 'COMPILER=' + str(cplr_name) + os.linesep )
        fp.write( 'MACHINE=' + str(mach_name) + os.linesep )
        fp.write( 'TEST_DIRECTORY=' + str(test_dir) + os.linesep )

        if inprogress:
            fp.write( 'IN_PROGRESS=True' + os.linesep )

        fp.write( os.linesep )
        dL = list( self.dataD.keys() )
        dL.sort()
        for d in dL:
          tD = self.dataD[d]
          tL = list( tD.keys() )
          tL.sort()
          for tn in tL:
            aD = tD[tn]
            s = d+'/'+tn + ' ' + make_attr_string( aD )
            fp.write( s + os.linesep )

        fp.close()

    def readResults(self, filename):
        """
        Loads the contents of the given file name into this object.
        A non-empty string is returned with an error message if the file
        format is unknown or not a test results format.
        """
        self.dataD = {}
        self.daterange = None
        self.dcache = {}

        fmt,vers,self.hdr,nskip = read_file_header( filename )

        if not fmt or fmt != 'results':
          raise Exception( "File format is not a single platform test " + \
                           "results format: " + filename )

        fp = open( filename, 'r' )
        n = 0
        d = None
        line = fp.readline()
        while line:
          if n < nskip:
            pass
          elif line.strip():
            if vers < 2:
              if line[:3] == "   ":
                L = line.split()
                tn = L[0]
                aD = read_attrs( L[1:] )
                self.addTestName( d, tn, aD )
              else:
                s = line.strip()
                if s: d = s
            else:
              L = line.split()
              d  = os.path.dirname( L[0] )
              tn = os.path.basename( L[0] )
              aD = read_attrs( L[1:] )
              self.addTestName( d, tn, aD )
          n += 1
          line = fp.readline()
        fp.close()

    def writeRuntimes(self, dirname, rootrel):
        """
        Writes all the tests that pass or diff in the runtimes format (which
        has a root-relative path in the header).  If 'rootrel' is None, the
        root relative path that is written is just the directory name of
        'dirname'.  This means that the resulting file would mark the
        top/root of a test source tree.
        """
        assert os.path.exists(dirname)
        assert os.path.isdir(dirname)

        filename = os.path.join( dirname, runtimes_filename )

        fp = open( filename, 'w' )
        fp.write( 'FILE_VERSION=results' + str(self.vers) + os.linesep )

        if rootrel == None:
            rootrel = os.path.basename( os.path.abspath(dirname) )
        fp.write( 'ROOT_RELATIVE=' + rootrel + os.linesep )
        rrL = rootrel.split('/')
        rrlen = len(rrL)

        fp.write( os.linesep )
        dL = list( self.dataD.keys() )
        dL.sort()
        for d in dL:
            # skip 'd' if it is not equal to or a subdirectory of rootrel
            if d.split('/')[:rrlen] == rrL:
                tD = self.dataD[d]
                tL = list( tD.keys() )
                tL.sort()
                for tn in tL:
                    aD = tD[tn]
                    # only write tests that pass or diff
                    if aD.get('result','') in ['pass','diff']:
                        s = d+'/'+tn + ' ' + make_attr_string( aD )
                        fp.write( s + os.linesep )

        fp.close()

    def mergeRuntimes(self, filename):
        """
        Reads the given results file and for each test therein, it overwrites
        the current test if the execution date is more recent.  If the test
        does not exist in this object yet, it is added.
        """
        fmt,vers,hdr,nskip = read_file_header( filename )

        if not fmt or fmt != 'results':
            raise Exception( "File format is not a single platform test " + \
                             "results format: " + filename )

        fp = open( filename, 'r' )
        n = 0
        d = None
        line = fp.readline()
        while line:
            if n < nskip:
                pass
            elif line.strip():
                if vers < 2:
                    if line[:3] == "   ":
                        L = line.split()
                        tn = L[0]
                        aD = read_attrs( L[1:] )
                        dt1 = self.testAttrs( d, tn ).get( 'xdate', 0 )
                        dt2 = aD.get( 'xdate', 0 )
                        if dt2 >= dt1:
                            self.addTestName( d, tn, aD )
                    else:
                        s = line.strip()
                        if s: d = s
                else:
                    L = line.split()
                    d  = os.path.dirname( L[0] )
                    tn = os.path.basename( L[0] )
                    aD = read_attrs( L[1:] )
                    dt1 = self.testAttrs( d, tn ).get( 'xdate', 0 )
                    dt2 = aD.get( 'xdate', 0 )
                    if dt2 >= dt1:
                        self.addTestName( d, tn, aD )
            n += 1
            line = fp.readline()
        fp.close()

    def _accumulate_date_range(self, attrD):
        ""
        xd = attrD.get( 'xdate', 0 )
        if xd > 0:
            if self.daterange == None:
                self.daterange = [ xd, xd ]
            else:
                self.daterange[0] = min( self.daterange[0], xd )
                self.daterange[1] = max( self.daterange[1], xd )


class MultiResults:

    def __init__(self, filename=None):
        """
        If the 'filename' is not None and it exists, it is read.
        """
        self.vers = 2

        # this dict comes from a results directory:
        #     dataD maps root-relative directory to testD
        #       testD maps test key to platD
        #         platD maps platform/compiler to attrD
        #           attrD maps attribute name to attribute value
        self.dataD = {}

        # 'rtimeD' comes from runtimes files contained at the top of the
        # test directory, and 'rtime_roots' is a list of the top directory
        # names
        #     rtimeD maps root-relative directory to testD
        #       testD maps test key to runtime
        self.rtimeD = {}
        self.rtime_roots = []

        # maps test name to a list of test directories
        self.tmap = {}

        # cache of test file directory to root-relative directory
        self.dcache = {}

        if filename:
          self.readFile(filename)

    def dirList(self):
        """
        Return a sorted list of root-relative directories stored in the
        database.
        """
        dL = list( self.dataD.keys() )
        dL.sort()
        return dL

    def testList(self, rootrel):
        """
        For a given root-relative directory, return a sorted list of test
        keys contained in that directory.
        """
        tD = self.dataD.get( rootrel, {} )
        tL = list( tD.keys() )
        tL.sort()
        return tL

    def platformList(self, rootrel, testkey):
        """
        For a given root-relative directory and a test key, return the list
        of platform/compilers stored for the test.
        """
        tD = self.dataD.get( rootrel, {} )
        pD = tD.get( testkey, {} )
        pL = list( pD.keys() )
        pL.sort()
        return pL

    def testAttrs(self, rootrel, testkey, platcplr):
        """
        For a given root-relative directory, test key, and platform/compiler,
        return the test attribute dictionary.
        """
        tD = self.dataD.get( rootrel, {} )
        pD = tD.get( testkey, {} )
        aD = pD.get( platcplr, {} )
        return aD

    def getTime(self, rootrel, testkey, platcplr):
        """
        Get the execution time of the given test.  If the test is not in the
        database, return None.
        """
        aD = self.testAttrs( rootrel, testkey, platcplr )
        t = aD.get( 'xtime', None )
        if t != None:
          return t, aD.get( 'result', None )
        return None,None

    def addTestName(self, rootrel, testkey, platcplr, attrD):
        """
        The 'rootrel' is the relative path from the master root directory
        to the directory containing the test specification file.

        The 'testkey' is the test name together with any parameter names and
        values.

        If the test already exists, it is overwritten.
        """
        assert rootrel and rootrel != '.'

        tD = self.dataD.get( rootrel, None )
        if tD == None:
          tD = {}
          self.dataD[rootrel] = tD
        pD = tD.get( testkey, None )
        if pD == None:
          pD = {}
          tD[testkey] = pD
        aD = pD.get( platcplr, None )
        if aD == None:
          aD = {}
          pD[platcplr] = aD
        else:
          aD.clear()
        aD.update( attrD )

        L = self.tmap.get(testkey,None)
        if L == None:
          L = []
          self.tmap[testkey] = L
        if L.count(rootrel) == 0:
          L.append( rootrel )

    def writeFile(self, filename):
        """
        Writes/overwrites the given filename with the contents of this object.
        """
        fp = open( filename, 'w' )
        fp.write( 'FILE_VERSION=multi' + str(self.vers) + os.linesep )

        fp.write( os.linesep )
        dL = list( self.dataD.keys() )
        dL.sort()
        for d in dL:
          tD = self.dataD[d]
          tL = list( tD.keys() )
          tL.sort()
          for tn in tL:
            pD = tD[tn]
            pL = list( pD.keys() )
            pL.sort()
            for pc in pL:
              aD = pD[pc]
              s = d+'/'+tn+' '+pc + ' ' + make_attr_string(aD)
              fp.write( s + os.linesep )

        fp.close()

    def readFile(self, filename):
        """
        Loads/merges the contents of the given file name into this object.
        """
        fmt,vers,self.hdr,nskip = read_file_header( filename )

        if not fmt or fmt != "multi":
          raise Exception( "File format is not a multi-platform test " + \
                           "results format: " + filename )
        if vers < 2:
          raise Exception( "Multi-platform test results format version " + \
                           "not supported: " + str(vers) )

        fp = open( filename, 'r' )
        n = 0
        line = fp.readline()
        while line:
            if n < nskip:
                pass
            elif line.strip():
                L = line.split()
                d  = os.path.dirname( L[0] )
                tn = os.path.basename( L[0] )
                pc = L[1]
                aD = read_attrs( L[2:] )
                self.addTestName( d, tn, pc, aD )
            n += 1
            line = fp.readline()

        fp.close()

    def getRootRelative(self, testkey ):
        """
        If the test identifier is contained in the test-to-directory map and
        there is only one directory, then that directory is determined to be
        the root relative directory for the test.
        """
        dL = self.tmap.get( testkey, None )
        if dL != None and len(dL) == 1:
          return dL[0]
        return None


def make_test_key( tspec ):
    ""
    key = os.path.basename( tspec.getDisplayString() )
    key = key.replace( ' ', '|' )
    return key


def read_file_header( filename ):
    """
    A header is:

      1. Any number of blank lines before the header
      2. Any number of KEY=value pairs (anything else is ignored)
      3. One or more blank lines stops the header

    Returns a tuple (format type, version integer, header dict, hdr lines),
    where the format type and version integer may be None if the header key
    "FILE_VERSION" was not found.  The header lines is the number of lines
    of header data in the file.
    """
    fp = open( filename, 'r' )

    cnt = 0
    hdr = {}
    line = fp.readline()
    while line:
      line = line.strip()
      if line[:5] == 'TEST:':
        break
      elif line:
        cnt += 1
        L = line.split('=',1)
        if len(L) == 2 and L[0].strip():
            if L[1].strip() == 'None':
                hdr[ L[0].strip() ] = None
            else:
                hdr[ L[0].strip() ] = L[1].strip()
      elif cnt > 0:
        break
      line = fp.readline()

    if type(filename) == type(''):
      fp.close()

    vers = hdr.get( 'FILE_VERSION', None )
    if vers:
      i = len(vers) - 1
      while i >= 0 and vers[i] in '0123456789':
        i -= 1
      t = vers[:i+1]
      n = 0
      sn = vers[i+1:]
      if sn:
        n = int(sn)
      return t,n,hdr,cnt

    return None,None,hdr,cnt


def file_rootrel(tdir):
    """
    Determines the root-relative directory of a test in 'tdir' by looking
    for a file called "runtimes" in 'tdir'; if it exists and has the
    ROOT_RELATIVE variable set, then the root relative path for the test is
    returned.  If it does not find "runtimes" in 'tdir', it traverses up
    looking for a "runtimes" file with ROOT_RELATIVE set.
    """
    r = None
    pL = []
    for i in range(256):
      fn = os.path.join( tdir, runtimes_filename )
      if os.path.exists(fn):
        try:
          fmt,vers,hdr,n = read_file_header(fn)
          r = hdr['ROOT_RELATIVE']
        except Exception:
          pass
        else:
          if len(pL) > 0:
            pL.insert( 0, r )
            r = os.path.join( *pL )
          break
      d,b = os.path.split( tdir )
      if not b or d == tdir:
        break
      pL.insert( 0, b )
      tdir = d
    return r


def _svn_rootrel(tdir):
    """
    Determines the root-relative directory of a test in 'tdir' by
    running svn and extracting the repository directory path, then
    applying hueristics on the path name.
    
    TODO: provide a mechanism to feed this routine the recognized
          repository roots instead of hard wiring it here
    """
    cdir = os.getcwd()
    try: os.chdir( tdir )
    except Exception: return None

    try:
        # run svn info to get the relative URL and the repository URL
        import subprocess

        p = subprocess.Popen( 'svn info', shell=True,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, close_fds=True )
        ip,fp = (p.stdin, p.stdout)

        url = None
        relurl = None
        repo = None
        line = fp.readline()
        while line:
          if line[:4] == 'URL:':
            url = line.split()[-1]
          elif line[:13] == 'Relative URL:':
            relurl = line.split()[-1]
          elif line[:16] == 'Repository Root:':
            repo = line.split()[-1]
          line = fp.readline()
        ip.close() ; fp.close()
    finally:
        os.chdir(cdir)

    if relurl == None:
      if url == None or repo == None:
        return None
      if len(url) < len(repo) or url[:len(repo)] != repo:
        return None
      relurl = '^'+url[len(repo):]

    # massage the relative URL to remove leading characters
    if relurl == '^':
      relurl = ''
    elif relurl[:2] == '^/':
      relurl = relurl[2:]
      if relurl:
        relurl = os.path.normpath( relurl )
        assert not os.path.isabs(relurl)

    # remove leading URL specification; the 'X' trick is because normpath()
    # does not seem to reduce a leading '//' to just a single '/'
    repo = os.path.normpath( 'X'+repo.split(':',1)[-1] )[1:]

    if repo == "/teamforge.sandia.gov/svn/repos/alegranevada":
      dL = relurl.split('/')
      if len(dL) >= 2 and \
         dL[0] == 'trunk' and \
         dL[1] in ['Benchmarks','nevada','alegra']:
        return '/'.join( dL[1:] )

    return None


def determine_rootrel( testspec, dcache ):
    """
    Uses the directory containing the test specification file to determine
    the directory path from the root directory down to this test.  The path
    includes the top level root directory name, such as Benchmarks/Regression/
    3D/comprehensive.  Returns an empty string if the path could not be
    determined.  The 'dcache' argument is a dictionary used for caching test
    directories to rootrel directories.
    """
    tdir = testspec.getDirectory()

    rootrel = dcache.get( tdir, None )

    if rootrel == None:
        rootrel = _svn_rootrel( tdir )
        if rootrel == None:
            rootrel = file_rootrel( tdir )
        if rootrel == None:
            # mark this directory so we don't waste time trying again
            rootrel = ''
        dcache[tdir] = rootrel

    return rootrel


class LookupCache:

    def __init__(self, platname, cplrname, resultsdir=None):
        ""
        self.platname = platname
        self.cplrname = cplrname
        self.resultsdir = resultsdir

        self.multiDB = None

        self.testDB = TestResults()
        self.srcdirs = {}  # set of directories scanned for TestResults
        self.rootrelD = {}  # maps absolute path to root rel directory

    def load(self):
        ""
        if self.resultsdir != None:
            f = os.path.join( self.resultsdir, multiruntimes_filename )
            self.multiDB = MultiResults()
            if os.path.exists(f):
                self.multiDB.readFile(f)

    def getRunTime(self, testspec):
        """
        Looks in the testing directory and the test source tree for files that
        contain a runtime for the given test.  If an entry is not found then
        None,None is returned.

        The 'cache' must be a LookupCache instance and should be the same instance
        for a set of tests (which helps performance).  Also, this same cache
        should be given/used by any approximate execution time algorithms if this
        function fails to find a runtime for the test.

        The algorithm looks for the test in this order:

          1. The TESTING_DIRECTORY directory multiplatform results file
          2. A test source tree runtimes file
        """
        assert self.platname
        if self.cplrname:
            platid = self.platname+'/'+self.cplrname
        else:
            platid = self.platname

        testkey = make_test_key( testspec )
        tdir = testspec.getDirectory()

        # the most reliable runtime will be in the testing directory, but for
        # that we need the test root relative directory

        rootrel = self.rootrelD.get( tdir, None )

        if rootrel == None:
          rootrel = file_rootrel( tdir )
          if rootrel == None:
            rootrel = _svn_rootrel( tdir )
            if rootrel == None:
              if self.multiDB != None:
                rootrel = self.multiDB.getRootRelative( testkey )
              if rootrel == None:
                rootrel = ''  # mark this directory so we don't try again
          self.rootrelD[tdir] = rootrel

        tlen = None
        result = None

        if rootrel and self.multiDB != None:
          tlen,result = self.multiDB.getTime( rootrel, testkey, platid )

        if tlen == None and rootrel:

          # look for runtimes in the test source tree

          d = testspec.getDirectory()
          if d not in self.srcdirs:

            while tlen == None:
              f = os.path.join( d, runtimes_filename )
              self.srcdirs[d] = None
              if os.path.exists(f):
                try:
                  fmt,vers,hdr,nskip = read_file_header( f )
                except Exception:
                  fmt = None
                if fmt and fmt == 'results':
                  self.testDB.mergeRuntimes( f )
                  break

              nd = os.path.dirname(d)
              if d == nd or not nd or nd == '/' or nd in self.srcdirs:
                break
              d = nd

          tlen = self.testDB.getTime( rootrel, testkey )

        return tlen, result


def make_attr_string( attrD ):
    """
    Returns a string containing the important attributes.
    """
    s = ''
    v = attrD.get('xdate',None)
    if v != None and v > 0:
      s = s + ' ' + '_'.join( time.ctime(v).split() )
    v = attrD.get('xtime',None)
    if v != None:
      s = s + ' xtime=' + str(v)
    v = attrD.get('state',None)
    if v != None:
      s = s + ' ' + v
      if v == "done":
        rs = attrD.get('result',None)
        if rs != None:
          s = s + ' ' + rs
    if 'TDD' in attrD:
        s += ' TDD'
    return s.strip()


def read_attrs( attrL ):
    """
    Returns a dictionary containing the attributes given in 'attrL' list of
    strings, which is string.split() of make_attr_string().
    """
    attrD = {}
    i = 0
    if i < len(attrL) and \
       attrL[i][:3] in ['Sun','Mon','Tue','Wed','Thu','Fri','Sat']:
        L = attrL[i].split('_')
        s = ' '.join(L)
        yr = int(L[-1])
        if yr < 2000:
            attrD['xdate'] = -1
        else:
            attrD['xdate'] = int( time.mktime( time.strptime(s) ) )
        i += 1
    if i < len(attrL) and attrL[i][:6] == "xtime=":
        attrD['xtime'] = int( attrL[i].split('=')[1] )
        i += 1
    if i < len(attrL) and attrL[i] in ['done','notrun','notdone']:
        st = attrL[i]
        attrD['state'] = st
        i += 1
        if st == "done" and i < len(attrL):
            attrD['result'] = attrL[i]
            i += 1
    if i < len(attrL) and attrL[i] == 'TDD':
        i += 1
        attrD['TDD'] = True
    return attrD


def merge_multi_file( multi, filename, warnL, dcut, xopt, wopt ):
    """
    """
    tr = MultiResults()
    try:
        tr.readFile( filename )
    except Exception:
        warnL.append( "skipping multi-platform results file " + \
                      filename + ": Exception = " + str(sys.exc_info()[1]) )
        tr = None

    newtest = False
    if tr != None:
        for d in tr.dirList():
            for tn in tr.testList(d):
                for pc in tr.platformList( d, tn ):
                    xD = multi.testAttrs( d, tn, pc )
                    aD = tr.testAttrs( d, tn, pc )
                    if merge_check( xD, aD, dcut, xopt, wopt ):
                        newtest = True
                        multi.addTestName( d, tn, pc, aD )

    return newtest


def merge_results_file( multi, filename, warnL, dcut, xopt, wopt ):
    """
    """
    tr = TestResults()
    try:
        tr.readResults( filename )
    except Exception:
        warnL.append( "skipping results file " + filename + \
                      ": Exception = " + str(sys.exc_info()[1]) )
        tr = None

    newtest = False
    if tr != None:
        plat = tr.platform()
        cplr = tr.compiler()
        if plat == None:
            warnL.append( "skipping results file "+filename + \
                          ": platform not defined" )
        else:
            if cplr:
                pc = plat+'/'+cplr
            else:
                pc = plat
            for d in tr.dirList():
                tL = tr.testList(d)
                for tn in tL:
                    xD = multi.testAttrs( d, tn, pc )
                    aD = tr.testAttrs( d, tn )
                    if merge_check( xD, aD, dcut, xopt, wopt ):
                        newtest = True
                        multi.addTestName( d, tn, pc, aD )

    return newtest


def merge_check( existD, newD, dcut, xopt, wopt ):
    """
    Return True if the new test should be merged in (based on the
    attribute dict of the existing and new test).
    """
    # new test must have a date, a runtime, and an acceptable result
    nd = newD.get('xdate',-1)
    nt = newD.get('xtime',-1)
    nr = newD.get('result',None)
    if nd > 0 and nt > 0 and nr in ['pass','diff','timeout']:

        xd = existD.get('xdate',-1)
        xt = existD.get('xtime',-1)
        xr = existD.get('result',None)

        if xd < 0 or xt < 0 or xr not in ['pass','diff','timeout']:
            return True

        if wopt:
            return True
        elif xopt:
            if nd >= xd:
                # new date is more recent, so take new test
                return True
        else:
            if xt < 0:
                return True
            if dcut != None:
                # with -d option, lower the precedence of old tests
                if xd < dcut and nd < dcut:
                    if nt > xt:
                        # both are old tests, so take max runtime
                        return True
                elif xd < dcut:
                    # existing test below cutoff, so take new test
                    return True
                elif nd < dcut:
                    pass  # new test below cutoff, so take old test
                else:
                    # both tests above cutoff, so take max runtime
                    if nt > xt:
                        return True
            elif nt > xt:
                # take test with maximum runtime
                return True

    return False


def date_round_down( tm ):
    """
    Given a date in seconds, this function rounds down to midnight of the
    date.  Returns a date in seconds.
    """
    s = time.strftime( "%Y %m %d", time.localtime( tm ) )
    T = time.strptime( s, "%Y %m %d" )
    return time.mktime( T )


def parse_results_filename( filename ):
    """
    Assuming a file name of the form

        results.<date>.<platform>.<options>.<tag>

    this function returns a tuple

        ( date, platform, options, tag )

    where an entry will be None if the filename form did not have that data or
    if parsing for that entry failed.  The 'date' is seconds since epoch.
    The rest are strings.
    """
    f = os.path.basename( filename )
    L = [ s.strip() for s in f.split('.',4) ]

    ftime = None
    if len(L) >= 2:
        try:
            T = time.strptime( L[1], '%Y_%m_%d' )
            ftime = time.mktime( T )
        except Exception:
            ftime = None

    platname = None
    if len(L) >= 3:
        platname = L[2]

    opts = None
    if len(L) >= 4:
        opts = L[3]

    tag = None
    if len(L) >= 5:
        tag = L[4]

    return ftime, platname, opts, tag


def read_results_file( filename, warnL ):
    """
    Constructs a TestResults class and loads it with the contents of
    'filename', which is expected to be a results.<date>.* file.  Returns
    the file date, the TestResults object, and the results key.  If the read
    fails, then None,None,None is returned and the 'warnL' list is appended
    with the error message.
    """
    # parse the file name to get things like the date stamp
    ftime,plat,opts,tag = parse_results_filename( filename )

    try:
        assert ftime != None

        # try to read the file
        fmt,vers,hdr,nskip = read_file_header( filename )
        assert fmt == 'results', \
                'expected a "results" file format, not "'+str(fmt)+'"'
        tr = TestResults( filename )

        # the file header contains the platform & compiler names
        assert tr.platform() != None

    except Exception:
        warnL.append( "skipping results file: " + filename + \
                                ", Exception = " + str(sys.exc_info()[1]) )
        return None,None,None

    results_key = plat
    if opts != None:
        results_key += '.'+opts
    if tag != None:
        results_key += '.'+tag

    return ftime,tr,results_key
