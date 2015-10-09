Project Tuscan
==============

Experiments for evaluating the compilability of a large corpus of
programs in various compilation environments:

* Different C libraries and compilers
* Different architectures
* Different platforms
* Static vs. dynamic linking


Each directory contains an experiment and its associated Dockerfile.
Running make inside each directory should be sufficient to launch that
experiment.  Within each directory, the directory 'logs' contains
timestamped log directories; each time an experiment is run, a symlink
to the latest log directory called 'logs/latest' is created for
convenience.


Directories
-----------

*   deps_graph:

    A python script and associated container that outputs dependency
    relationships between all Arch Linux packages. This only needs to be
    run once, although it's fairly speedy.



Dependencies
------------

*   docker

    (you should add your user to the 'docker' group)
