## 2.1.5 (2016.02.16)

Bugfixes:
  - Stop filtering out `-m` options (@joshtriplett, #115)
  - Updated man page bugs section (#114)


## 2.1.4 (2016.02.14)

Bugfixes:
  - Make paths to sources and include files absolute. (@svenpanne, #111)
  - Extend known issues section of documentation (#112, #108, #105, #102)


## 2.1.3 (2016.01.13)

Bugfixes:
  - warnings are not filtered from output (@velkyel, #106)
  - support universal binaries (32 and 64) on x86 OS X (@DeanoC, #101)


## 2.1.2 (2015.10.01)

Bugfixes:
  - Fix escaping quotes for shell too. (@zauguin, #88)


## 2.1.1 (2015.08.31)

Bugfixes:
  - Fix iterator next method usage (@drvink, #97)


## 2.1.0 (2015.08.08)

Features:
  - Ignore preprocessor flags for dependency generation (@jonthn, #74)
  - Exclude irrelevant files names in command (@wweic, #94)
  - Support MetaWare toolkit (@twpedersen, #95)
  - Use docker build for travis-ci

Bugfixes:
  - Get rid of cmake warnings on osx (@emlai, #90)
  - Protect report generation in multithread build systems (@smoofra, #93)


## 2.0.4 (2015-06-16)

Bugfixes:

  - Fix crash when make with -j option (@minhyuk, #87)


## 2.0.3 (2015-04-04)

Bugfixes:

  - Fix passing of arguments to mkdtemp (@kljohann, #75)
  - Empty output when compiler used to link. (@QuaziRandom, #80)
  - Bad escape of strings in compilation database. (@jumapico, #81)


## 2.0.2 (2015-02-08)

Bugfixes:

  - Address Sanitizer error fixed.
  - Fix some typos in man page (@sebastinas, #72)


## 2.0.1 (2015-01-23)

Bugfixes:

  - Double free problem fixed when descrutor called multiple times.


## 2.0 (2015-01-20)

Features:

  - Rewrite command `bear` from C to Python.
  - Simplified build process with a single module for `libear`.

Bugfixes:

  - Work with empty environment (#69, @YorkZ)
  - Filter out redundant entries (#66, @HongxuChen)
  - Append to existing compilation database (#63, @p0rnfl4k3s)

## 1.4.4 (2015-01-09)

Features:

  - Improve escaping logic (#67, #68, @SpecLad)
  - Reword README file to be more english (#64, @libnoon)


## 1.4.3 (2014-07-11)

Features:

  - Automatically generate Debian package dependency list with cpack (#62, @bbannier)


## 1.4.2 (2014-05-19)

Features:

  - cross compilers recognised by bear (@nolange)


## 1.4.1 (2014-05-09)

Bugfixes:

  - fix output entries have c14n file path (#61, @nickhutchinson)
  - fix error message on missing config file (#60, @viraptor)
  - extend README file based on user feedbacks (#54, #55, #56, #59, @btorpey, @breser, @vguerra)


## 1.4 (2014-01-12)

Bugfixes:

  - fix typo in the README.md (#48, @breser)
  - fix typo in the man page (#49, @sebastinas)
  - fix cmake file to honor given CFLAGS (#50, @sebastinas)
  - fix execle causes segfault on 32 bit systems (#51, #52, @breser, @sebastinas)


## 1.3 (2013-12-18)

Features:

  - set empty cancel parameter list as default (#39, #43)
  - implement verbose filter message at the end of the run (#41)

Bugfixes:

  - fix process stops when ctrl-z pressed (#40, @bbannier)
  - fix non filtered output option renamed from debug (#44, @mikemccracken)
  - fix broken build on OS X (#46, @breser)
  - fix documentation (@mlq)
  - fix posix_spawn* call not implemented (#43, @agentsim, @apoluektov)


## 1.2 (2013-10-01)

Features:

  - dependency file generation compiler calls are _optionally_ filtered (#35, @lonico)
  - use config file for compiler call filtering parameters (#38, @lonico, @peti)

Bugfixes:

  - fix end-to-end test on OS X (#37, @smmckay)
  - fix memory leaks detected by static analyser


## 1.1 (2013-08-01)

Features:

  - dependency file generation compiler calls `-M` are filtered (#35, @chrta)
  - smaller memory footprint (less allocation, code went for places when it is called)
  - add version query to command line

Bugfixes:

  - fix memory leaks detected by static analyser


## 1.0 (2013-06-27)

Features:

  - change license to GPLv3

Bugfixes:

  - fix process syncronization problem (#33, @blowback)
  - fix malloc/realloc usage (#34, @mlq)


## 0.5 (2013-06-09)

Features:

  - use temporary directory for default socket (#29, @sebastinas)

Bugfixes:

  - fix bashism in test (#27, @sebastinas)
  - fix temporary socket dir problem introduce by new code (#31, @lukedirtwalker)
  - fix bug introduced by report filtering (#32, @lukedirtwalker)


## 0.4 (2013-04-26)

Features:

  - man page generation is optional (#18, @Sarcasm)
  - port to OS X (#24, @breser)

Bugfixes:

  - fix json output on whitespaces (#19)
  - fix socket reading problem (#20, @brucestephens)
  - improved signal handling (#21)
  - build system checks for available `exec` functions (#22)


## 0.3 (2013-01-09)

Features:

  - query known compilers which are play roles in filtering (#10)
  - query recognised source file extensions which are filtering (#11)
  - man page added (#12)
  - pacage generation target added to `cmake` (#15)

Bugfixes:

  - fix child process termination problem
  - test added: build result propagation check


## 0.2 (2013-01-01)

Features:

  - add debug output

Bugfixes:

  - test added: unit test, end-to-end test and full `exec` family coverage (#4)
  - `scons` does pass empty environment to child processes (#9)
  - fix `execle` overriding bug (#13)
  - fix json output (#14)


## 0.1 (2012-11-17)

Features:

  - first working version
  - [Travis CI](https://travis-ci.org/rizsotto/Bear) hook set up
