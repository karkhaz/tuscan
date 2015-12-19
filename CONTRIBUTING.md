
Contributing to tuscan
======================

This document contains recipes for common tasks when adding to the
experiment.


## Adding a new toolchain

Summary:

- Add a directory `toolchains/$TOOLCHAIN_NAME`
- That directory should contain:
  - `setup.py`, containing method `toolchain_specific_setup(args)`
  - `Dockerfile`
  - `makepkg.conf`

### Usage

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
  appropriately chowned or chmodded. See `toolchains/android/setup.py`
  for an example.

- `Dockerfile` is the Dockerfile for the `make_package` stage, i.e. it
  sets up the container where packages are built.

  - The most notable feature in `toolchains/android/Dockerfile` is
    passing environment variables to the stage with the --env-vars
    switch. Any environment variables passed this way will be passed
    directly to makepkg. It is not recommended to set environment
    variables in `makepkg.conf`, as this is somewhat unreliable.

- `makepkg.conf` can in most cases just be copied from vanilla. One can
  use it, for example, to set the -j flag for Make.
