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

Tuscan uses a mirror of Arch Linux binaries and sources.

### Binaries

Tuscan expects that a mirror Arch Linux binaries exists in the top-level
directory, named `mirror`. If you obtain a copy of Arch Linux binaries
from your local mirror, you may wish to remove i386 binaries to save
space.

### Sources

By default, Tuscan downloads sources of Arch Linux packages into a data
container called `sources` as it runs, so you don't need to provide
this.

If you have atomically downloaded a copy of all Arch sources and wish to
add it to Tuscan, you will need to add it to the sources data container.

1. Create the data container if it doesn't already exist:

        docker create -v /sources --name sources base/arch /bin/true

1. Spin up a docker container that mounts the data container as well as
   the local sources directory, and copies the contents of the sources
   directory into the container:

        docker run --volumes-from sources -v \
          $(pwd)/tmp_sources:/tmp_sources base/arch \
          sh -c 'cp /tmp_sources/* /sources'



Running Tuscan
--------------

Generating data for a toolchain:

    ./tuscan.py build TOOLCHAIN

The names of toolchains are subdirectories of `toolchains/`. Currently,
the only toolchain is `vanilla`, which builds Arch Linux packages using
the default compiler and standard libraries.

Post-processing the data from a build:

    ./tuscan.py post

The resulting JSON files are dumped in the `post/TOOLCHAIN` directory,
one file per package. The schema for the resulting JSON file is
described by the `post_processed_schema` structure in
`tuscan/schemata.py`.

Generating a HTML report from post-processed data:

    ./tuscan.py html

The resulting HTML pages are dumped in the `html/TOOLCHAIN` directory,
one page per package.


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

*   docker

    (you should add your user to the 'docker' group)

*   ninja

    http://martine.github.io/ninja/

*   PyYAML

    http://pyyaml.org/


*   Jinja2

    http://jinja.pocoo.org/docs/dev/


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
