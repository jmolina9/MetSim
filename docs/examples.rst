.. _examples:

Examples
========

Basics
------
Provided in the source are several examples that can help you to
get started using MetSim. They are located in the ``examples``
directory.  We will look at the ``example_nc.conf`` file.  Its
contents are:

.. code-block:: ini

    # This is an example of an input file for MetSim
    [MetSim]

    # Time step in minutes
    time_step = 60

    # Forcings begin here (year/month/day:hour)
    start = 1950/1/1:0

    # Forcings end at this date (year/month/day)
    stop = 1950/1/31

    # Input specification
    forcing = ./tests/data/test.nc
    domain  = ./tests/data/domain.nc
    state = ./tests/data/state_nc.nc
    in_fmt = netcdf
    domain_fmt = netcdf
    state_fmt = netcdf

    # Output specification
    out_fmt = netcdf
    out_dir = ./results
    out_state = ./results/state.nc
    out_prefix = forcing
    out_precision = f8

    # How to disaggregate
    method = mtclim

    [forcing_vars]
    Prec = prec
    Tmax = t_max
    Tmin = t_min

    [state_vars]
    prec = prec
    t_max = t_max
    t_min = t_min

    [domain_vars]
    lat = lat
    lon = lon
    mask = mask
    elev = elev

This is a minimal configuration file for MetSim, and contains 3 sections.  The
first section, ``[MetSim]`` describes some basic settings such as the locations
of data and parameters used in calculations.  For a complete description of the
input format see :ref:`configuration`.  The key things to note in this section
are the options specified under the ``# Input specification`` and ``# Output
specification`` comment headers.  The ``forcing`` and ``domain`` options refer
to the two types of required input, and the ``in_format`` and ``out_format``
options tell MetSim how they should be treated.

The second and third sections (``[forcing_vars]`` and ``[state_vars]``) describe the variables in the
datasets provided in the ``forcing`` and ``state`` options of the first section.
The left side of the assignment is the name of the variable given
in the ``forcing`` dataset, while the right hand side is the
name the variable should be given within MetSim.  Note that the
variables shown here are the minimum required set to run the
forcing generation. The names given on the right hand side are
also important to name correctly, as they are referenced internally.
If you are unsure what variable names are used internally see the
:ref:`configuration` page for a full breakdown.

To run this example from the command line, once you have installed
MetSim, use the following command:

``ms path/to/example_nc.conf --verbose``

This will run MetSim and disaggregate to hourly data, and write
out the results in a NetCDF file located in the directory specified
under ``out_dir`` in the configuration file (here ``./results``).
The addition of the ``--verbose`` flag provides some
information back to you as MetSim runs.  In the absence of this
flag MetSim will quietly run in the background until finished, or
some error has occurred.


Generating daily values
-----------------------
Daily values can be output by specifying a ``time_step`` of ``1440`` in the
configuration file, such as the one shown in the previous section. This will
prevent MetSim's disaggregation routines from being run, and the results written
out will be daily values.

Translating formats of daily values
-----------------------------------

.. warning:: This section `only` applies to daily input and output.

This section can be useful if you are interested in converting VIC format binary
or ASCII forcing inputs into NetCDF format.

To configure this behavior, several configuration options will have to be set.
First, the ``time_step`` variable must be set to ``1440`` to enable daily output.
Then, the ``forcing_fmt`` and ``out_fmt`` variables should be specified. The final
option that should be set is ``out_vars``.  This can be set to include only the
variables you have in your input file, if you wish to not generate any new data,
or it can be set to include any of the variables generated by the simulator
specified in the ``method`` option.
