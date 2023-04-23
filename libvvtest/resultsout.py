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

    def prerun(self, atestlist, verbosity):
        ""
        for wr in self.writers:
            wr.prerun( atestlist, verbosity )

    def midrun(self, atestlist):
        ""
        for wr in self.writers:
            wr.midrun( atestlist )

    def postrun(self, atestlist):
        ""
        for wr in self.writers:
            wr.postrun( atestlist )

    def info(self, atestlist):
        ""
        for wr in self.writers:
            wr.info( atestlist )
