
# vvtest

**vvtest** is a test harness specialized for running regression, validation,
and verification tests on high performance computing (HPC) platforms.

At a high level, **vvtest** just selects and runs scripts, called tests.
It is the test specification and management capabilities together with the
plugin and control features that enable the execution of complex tests on
workstations up to large HPC platforms.

Notable features include:
* Pure Python, compatible with versions 2.6+ and 3.x
* Built-in CPU & GPU resource management and load balancing
* Built-in support for HPC batch queuing systems, such as SLURM and LSF
* Test parameterization, allowing a single script file to produce multiple
  test instances with different parameter values
* Inter-test dependencies - tests can depend on other tests. Dependencies
  are run first and the results are available to the dependent test.
* Test selection and execution control, such as by keyword, parameter,
  platform, and a general option string
* Tests can be any script language, but there is built-in support for Python
  and (to a lesser extent) Bash
* Configuration and plugins allow control over testing behavior
* Tests are executed in a separate directory from the test scripts
  ("out of source" execution)
* Test result output formats include CDash, GitLab markdown, JUnit, and HTML.


## Documentation

* Run `vvtest -h` to show the options.
* The RELEASE_NOTES file is kept up to date.
* Additional documentation is available on the wiki.


## Download and Install

Since the only dependency is Python, just clone the
**vvtest** repository and run the `vvtest` script. You can optionally run the
`install_vvtest` script to install into a prefix of your choice.


## An Example

Consider a file called `mytest.vvt` with contents
```
# This is my cool test.
#VVT: parameterize: np = 1 2

import vvtest_util as vvt
import shared_stuff as stuff

print ( 'Starting test {0} np={1}'.format( vvt.NAME, vvt.np ) )

stuff.run_simulation( myoption='foo', numcpu=vvt.np )
stuff.check_results()
```
This test could be run as follows:
```
$ vvtest mytest.vvt
==================================================
Test list:
    completed: 0
    notrun: 2
    total: 2

Platform ceelan, num procs = 16, max procs = 16
Start time: Fri Jun  5 18:07:34 2020
Starting: TestResults.ceelan/mytest.np=2
Starting: TestResults.ceelan/mytest.np=1
Finished: pass        0:01 06/05 18:07:34 TestResults.ceelan/mytest.np=2
Finished: pass        0:01 06/05 18:07:34 TestResults.ceelan/mytest.np=1
Progress: 2/2 = %100.0, time = 1s

==================================================
Summary:
    completed: 2
          2 pass
    total: 2

Finish date: Fri Jun  5 18:07:35 2020 (elapsed time 2s)
Test directory: TestResults.ceelan
```
Note that the test specification file, `mytest.vvt`, resulted in two test
instances, `mytest.np=1` and `mytest.np=2`, which were run and both passed.
A test can import the `vvtest_util.py` file, which is specific to each
test and contains information about the test instance and runtime parameters.

The test is run in a subdirectory to keep the output and artifacts separate.
```
$ ls -F TestResults.ceelan/mytest.np=2
execute.log  mytest.vvt@  vvtest_util.py  vvtest_util.pyc  vvtest_util.sh
```
The output from the test script (both stdout and stderr) is contained in
the file `execute.log`.


## History

**vvtest** evolved from Mike Wong's test infrastructure in the late 1990s,
through a python rewrite in the mid 2000s, to a refactoring in 2016 to
make it a project independent utility.


## Copyright

Copyright 2018 National Technology & Engineering Solutions of Sandia, LLC
(NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
Government retains certain rights in this software. 

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer. 

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution. 

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
