#!/usr/bin/env python

# Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
# (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.


class ResultsWriters:

    def __init__(self):
        ""
        self.writers = []

    def addWriter(self, writer):
        ""
        self.writers.append( writer )

    def prerun(self, atestlist, rtinfo, verbosity):
        ""
        for wr in self.writers:
            wr.prerun( atestlist, rtinfo, verbosity )

    def midrun(self, atestlist, rtinfo):
        ""
        for wr in self.writers:
            wr.midrun( atestlist, rtinfo )

    def postrun(self, atestlist, rtinfo, rtconfig=None):
        ""
        for wr in self.writers:
            wr.postrun( atestlist, rtinfo, rtconfig=rtconfig )

    def info(self, atestlist, rtinfo):
        ""
        for wr in self.writers:
            wr.info( atestlist, rtinfo )
