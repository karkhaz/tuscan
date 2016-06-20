
Contributing to tuscan
======================

This document contains recipes for common tasks when adding to the
experiment.


## Adding a new toolchain

Summary:

- Add a directory `toolchains/install_bootstrap/$TOOLCHAIN_NAME`
- That directory should contain:
  - `setup.py`, containing method `toolchain_specific_setup(args)`
  - `Dockerfile`
  - `makepkg.conf`
  - `tool_redirect_rules.yaml`
- Add a directory `toolchains/make_package/$TOOLCHAIN_NAME`
- That directory should contain:
  - `Dockerfile`
  - `makepkg.conf`

### toolchains/install_bootstrap/$TOOLCHAIN_NAME

This directory contains files that will be accessible to the
`install_bootstrap` stage.

- `setup.py` is used to install the toolchain. You must write a method
  called `toolchain_specific_setup`, which shall be run at the end of
  the `install_bootstrap` stage.

  Things you can assume about the environment in which
  `toolchain_specific_setup` is run:

  - Anything that is changed by the file
    `stages/install_bootstrap/main.py`. In particular, there will be a
    user called `tuscan` and a directory called `toolchain_root`.

  - Packages in the bootstrap set will already have been installed. You
    can also install any additional packages that you need by running
    `pacman -S` as usual.

  Things that are expected to be true after `toolchain_specific_setup`
  returns:

  - The toolchain has been correctly installed.

  Note that packages are built by the user `tuscan`, not by `root`. So
  any files that need to be accessible to the build should be
  appropriately chowned or chmodded. See
  `toolchains/install_bootstrap/android/setup.py` for an example.

- `Dockerfile` sets up the `install_bootstrap` container. This will be
  fairly similar across toolchains, as it will just invoke the `main.py`
  of the `install_bootstrap` stage. One way in which Dockerfiles may
  vary across toolchains is in what files are copied into the container;
  for example, the `musl` toolchain runs a separate setup script.

- `tool_redirect_rules.yaml` is a file describing which native tools will
  be overwritten by a compiler wrapper. Broken build scripts will often
  hard-code the path to a compiler or other native tool; tuscan thus
  replaces the native tools with a compiler wrapper that emits an error
  message and then invokes the toolchain-specific tools. The file format
  of `tool_redirect_rules.yaml` is described by the `binutil_schema` data
  structure in `tuscan/schemata.py`.

  - For example, if your toolchain supplies an archiver called `ar`,
    and you wish to clobber `/usr/bin/ar` so that it points to your
    toolchain's `ar`, then you would add `ar` to the `overwrite` array
    of the YAML file.

  - If your toolchain provides a compiler (e.g. `clang`) and you wish to
    override the default system compiler (`gcc`), then you would add
    `gcc: clang` (and also `cc: clang`) to the `replacements` dictionary
    of the YAML file.

  - The directory where all your toolchain's tools reside should be the
    value of the `bin` key of the YAML file, e.g.
    `bin: /toolchain_root/my_toolchain/bin`.


### toolchains/make_package/$TOOLCHAIN_NAME

This directory contains files that will be accessible to the
`make_package` stage.

- `Dockerfile` is the Dockerfile for the `make_package` stage, i.e. it
  sets up the container where packages are built.

  - The most notable feature in `toolchains/android/Dockerfile` is
    passing environment variables to the stage with the --env-vars
    switch. Any environment variables passed this way will be passed
    directly to makepkg. It is not recommended to set environment
    variables in `makepkg.conf`, as this is somewhat unreliable.

- `makepkg.conf` can in most cases just be copied from vanilla. One can
  use it, for example, to set the -j flag for Make.
