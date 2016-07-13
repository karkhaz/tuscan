Project Tuscan
==============

Experiments for evaluating the compilability of a large corpus of
programs in various compilation environments:

* Different C libraries and compilers
* Different architectures
* Different platforms
* Static vs. dynamic linking


Initial setup
-------------

Tuscan uses a [fork](https://github.com/karkhaz/Bear) of the
[libEAR](https://github.com/rizsotto/Bear) project as a submodule. You
will thus need to pass the `--recursive` switch to the `git clone`
command when cloning Tuscan, or else run `git submodule init; git
submodule update` after you have cloned it.

On the first run, Tuscan will attempt to download a copy of every
official Arch Linux binary package, as well as their corresponding
sources. These files are placed in the `mirror` and `sources` directory,
respectively. During the first run, Tuscan will also create and commit
an Arch Linux Docker image called `tuscan_base_image`, whose software
databases are in sync with the downloaded sources and binaries.  _Do not
remove this image_ from your system; if you do, you will need to
re-create it and also re-download up-to-date versions of the sources and
binaries.

Occasionally, downloads of a source or binary may fail; when this
happens for a particular package, a `$PACKAGE_NAME.log` file will be
left in the `sources` or `mirror` directory, containing information on
the failure.

- For binaries, you may wish to download the binary yourself and place
  it in the `mirror` directory. An archive of all Arch Linux binaries is
  hosted at the [Arch Archive](https://archive.archlinux.org/packages/);
  make sure that the version number that you're downloading matches the
  version described in the `.log` file.

- A failed download of a source file usually indicates that the upstream
  source is broken. It may be appropriate to file a bug about this on
  the [Arch Linux bug tracker](https://bugs.archlinux.org/). There is
  not much that can be done about this; Tuscan will fail to build that
  package and any packages that depend on it.

Binaries are downloaded from an Arch Linux mirror. If you don't live in
the United States, you may wish to replace "United States" in the
`stages/create_base_image/main.sh` script. The invocation of `reflector`
in that script finds the fastest and most up-to-date Arch mirrors from
the specified country.


Running Tuscan
--------------

Generating data for a toolchain:

    ./tuscan.py build TOOLCHAIN

The names of toolchains are subdirectories of `toolchains/`. Currently,
the only toolchain is `vanilla`, which builds Arch Linux packages using
the default compiler and standard libraries.

Post-processing the data from a build:

    ./tuscan.py post

The resulting JSON files are dumped in the `output/post/TOOLCHAIN`
directory, one file per package. The schema for the resulting JSON file
is described by the `post_processed_schema` structure in
`tuscan/schemata.py`.

Generating a HTML report from post-processed data:

    ./tuscan.py html

The resulting HTML pages are dumped in the `output/html/TOOLCHAIN`
directory, one page per package.

Generating figures from post-processed data:

    ./tuscan.py figures

The resulting figures are dumped in the `output/figures` directory.

Structure / Contributing
------------------------

Tuscan is structured as a set of *stages* under the `stages/` directory.
These are scripts that are run inside Arch Linux containers, performing
tasks on Arch Linux packages. These tasks include dependency resolution
and setting up a build environment for the chosen toolchain.

The final outcome is that every package in the official Arch Linux
repository is built with a particular toolchain, in reverse dependency
order. Packages that have been built successfully are added to a local
package repository, so that packages that depend on them can install
them later.

The stages write a `makepkg.ninja` file that describes dependency
relationships between Arch Linux packages.

Some stages depend on other stages having been run before they
themselves are run. Some stages also depend on +data-only containers+
having been created. For each experiment, these dependencies are
described in the file `stages/$STAGE_NAME/deps.yaml`.


Dependencies
------------

Software:

*   docker

    (you should add your user to the 'docker' group)

*   gnuplot

    http://gnuplot.info

Tuscan also requires several Python packages. These can be installed
with `pip`. Tuscan code that runs on your host machine is written in
Python 2, so if your operating system uses Python 3 by default you may
need to install these packages with `pip2`.

*   ninja

    http://martine.github.io/ninja/

*   PyYAML

    http://pyyaml.org/

*   Jinja2

    http://jinja.pocoo.org/docs/dev/

*   docker-py

    https://github.com/docker/docker-py


Troubleshooting
---------------

* Circular dependencies

  If the ninja build for package `foo` fails because the
  `bar.pkg.tar.xz` file could not be found, this is likely due to a
  circular dependency (`foo` makedepends on, and is makedepended on by,
  `bar`). This can be confirmed by reading the PKGBUILDs for `foo` and
  `bar`: search for these packages on www.archlinux.org/packages, and
  then browse to the PKGBUILD by clicking on the `Source Files` link.

  This issue can be fixed by adding `foo` and `bar` to the
  `circular_dependency_breakers` array in `get_base_package_names`.

* Provider packages

  Sometimes `foo` will depend on `bar`, but `deps_to_ninja` will not
  find any package called `bar` in the Arch Build Repository. More
  precisely, there will be no PKGBUILD in the ABS such that the PKGBUILD
  contains `bar` in its `pkgname` array, which would seem to indicate
  that package `bar` does not get built by any PKGBUILD.

  In fact, this could be because `bar` is a _metapackage_, that is, a
  package __provided__ by another package `baz`. An example is
  `sh`---many packages depend on `sh`, but in practice this package is
  provided by `bash`. More precisely, the PKGBUILD for `bash` will
  contain `provides=(... "sh" ...)` somewhere in the PKGBUILD.

  The current solution to this is to add `"sh" : "bash"` to the
  `provides` hash in `provides.py` whenever this causes a problem. These
  instances are hard to detect automatically because they require
  parsing the PKGBUILD (a bash script), since the `provides` array might
  be hidden inside a `package_` function.
