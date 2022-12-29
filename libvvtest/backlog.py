#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.


class TestBacklog:
    """
    Stores a list of TestCase objects.  They are sorted in descending order
    using keys (num procs, runtime)
    """

    def __init__(self):
        ""
        self.tests = []

    def insert(self, tcase):
        """
        Note: to support streaming, this function would have to do a
              sorted insert rather than an append
        """
        self.tests.append( tcase )

    def sort(self):
        ""
        self.tests.sort(
                key=lambda tc: [ tc.getSize()[0], tc.getStat().getRuntime(0) ],
                reverse=True )

    def pop(self):
        ""
        return self._pop_test( None )

    def pop_by_size(self, maxsize):
        ""
        constraint = TestConstraint( maxsize )
        return self._pop_test( constraint )

    def consume(self):
        ""
        while len( self.tests ) > 0:
            tcase = self.tests.pop( 0 )
            yield tcase

    def iterate(self):
        ""
        for tcase in self.tests:
            yield tcase

    def _pop_test(self, constraint):
        ""
        tcase = None

        if constraint:
            idx = self._get_starting_index( constraint.getMaxNP() )
        else:
            idx = 0

        while idx < len( self.tests ):
            if constraint is None or constraint.apply( self.tests[idx] ):
                tcase = self.tests.pop( idx )
                break
            idx += 1

        return tcase

    def _get_starting_index(self, max_np):
        ""
        if max_np == None:
            return 0
        else:
            return bisect_left( self.tests, max_np )


class TestConstraint:

    def __init__(self, maxsize):
        ""
        self.maxsize = maxsize

    def getMaxNP(self):
        ""
        if self.maxsize == None:
            return None
        else:
            return self.maxsize[0]

    def apply(self, tcase):
        ""
        if self.maxsize != None:

            np,nd = tcase.getSize()
            maxnp,maxnd = self.maxsize

            if np > maxnp or nd > maxnd:
                return False

        if tcase.isBlocked():
            return False

        return True


def bisect_left( tests, np ):
    ""
    lo = 0
    hi = len(tests)
    while lo < hi:
        mid = (lo+hi)//2
        if np < tests[mid].getSize()[0]: lo = mid+1
        else: hi = mid
    return lo

# To insert into the sorted test list, a specialization of insort_right is
# needed.  The comparison is based on np, and the list is in descending order.
# This function is just the python implementation of bisect.insort_right()
# and would need to be modified to work for this use case.
# def insort_right( a, x, less_than ):
#     ""
#     lo = 0
#     hi = len(a)
#     while lo < hi:
#         mid = (lo+hi)//2
#         if less_than( x, a[mid] ): hi = mid
#         else: lo = mid+1
#     a.insert(lo, x)
