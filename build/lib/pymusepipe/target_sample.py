# Licensed under a MIT style license - see LICENSE.rst

"""MUSE-PHANGS target sample module
"""

__authors__   = "Eric Emsellem"
__copyright__ = "(c) 2017, ESO + CRAL"
__license__   = "MIT License"
__contact__   = " <eric.emsellem@eso.org>"

# Standard modules
import os
from os.path import join as joinpath

import numpy as np

from src.pymusepipe import util_pipe as upipe
from src.pymusepipe import MusePipe
from src.pymusepipe import (PHANGS_reduc_config,
                            default_short_PHANGS_filter_list,
                            default_short_filter_list)
from src.pymusepipe.init_musepipe import InitMuseParameters
from src.pymusepipe.combine import MusePointings
from src.pymusepipe import rotate_pixtables
from .prep_recipes_pipe import dic_products_scipost
from .version import __version__ as version_pack

from astropy.table import Table

# ----------------- Galaxies and Pointings ----------------#
# Sample of galaxies
# For each galaxy, we provide the pointings numbers and the run attached to that pointing
dic_SAMPLE_example = {
        "NGC628": ['P100', {1:0, 2:0, 3:0, 4:0, 5:0, 6:0, 7:0, 8:0, 9:0, 10:0, 11:0, 12:0}],
        "NGC1087": ['P101', {1:1}], 
        }
# ----------------- Galaxies and Pointings ----------------#

#=============== Useful function ==========================#
def insert_suffix(filename, suffix=""):
    """Create a new filename including the 
    suffix in the name

    Input
    -----
    filename: str
    suffix: str
    """
    # Create new name
    sfilename, extension = os.path.splitext(filename)
    return "{0}_{1}{2}".format(sfilename, suffix, extension)


def update_calib_file(filename, subfolder="", folder_config=""):
    """Update the rcfile with a new root

    Input
    -----
    filename: str
        Name of the input filename
    folder_config: str
        Default is "". Name of folder for filename
    subfolder: str
        Name of subfolder to add in the path
    """
    full_filename = joinpath(folder_config, filename)
    if full_filename is None:
        upipe.print_error("ERROR: input filename is None")
        return ""

    # Testing existence of filename
    if not os.path.isfile(full_filename) :
        upipe.print_error("ERROR: input filename {inputname} cannot be found. ".format(
                            inputname=full_filename))
        return ""

    # If it exists, open and read it
    old_rc = open(full_filename)
    lines = old_rc.readlines()

    # Create new file
    new_filename = insert_suffix(full_filename, subfolder)
    new_rc = open(new_filename, 'w')

    # loop on lines
    for line in lines :
        sline = line.split()
        if sline[0] != "root":
            new_rc.write(line)
            continue
        if not os.path.isdir(sline[1]):
            upipe.print_warning("{} not an existing folder (from rcfile)".format(sline[1]))

        newline = line.replace(sline[1], joinpath(sline[1], subfolder))
        new_rc.write(newline)

    new_rc.close()
    old_rc.close()
    return new_filename
#------------ End of Useful functions -------------#

####################################################
# Defining Dictionary with running functions
####################################################
class PipeDict(dict) :
    """Dictionary with extra attributes
    """
    def __init__(self, *args, **kwargs) :
        self.update(*args, **kwargs)
        self._initialised = False

    def __setitem__(self, key, value):
        """Setting the item by using the dictionary of the new values
        """
        for funcname in dir(value):
            if callable(getattr(value, funcname)) and ("run" in funcname):
                setattr(self, funcname, self.run_on_all_keys(funcname))

        super(PipeDict, self).__setitem__(key, value)

    def update(self, *args, **kwargs):
        if args:
            if len(args) > 1:
                raise TypeError("update expected at most 1 arguments, "
                                "got %d" % len(args))
            other = dict(args[0])
            for key in other:
                self[key] = other[key]
        for key in kwargs:
            self[key] = kwargs[key]

    def setdefault(self, key, value=None):
        if key not in self:
            self[key] = value
        return self[key]

    def run_on_all_keys(self, funcname):
        """Runs the given function on all the keys
        """
        def _function(**kwargs):
            for key in self:
                getattr(self[key], funcname)(**kwargs)

        return _function

####################################################
# Defining classes to get samples and objects
####################################################
class MusePipeTarget(object):
    def __init__(self, targetname="",
                 subfolder='P100', list_pointings=None):
        self.targetname = targetname
        self.subfolder = subfolder
        self.list_pointings = list_pointings
        self.pipes = PipeDict()

class MusePipeSample(object):
    def __init__(self, TargetDic, rc_filename=None, cal_filename=None, 
            folder_config="", first_recipe=1, **kwargs) :
        """Using a given dictionary to initialise the sample
        That dictionary should include the names of the targets
        as keys and the subfolder plus pointings to consider

        Input
        -----
        TargetDic: dic
            Dictionary of targets. Keys are target names.
            Values for each target name should be a list of 2 parameters.
                - The first one is the name of the subfolder (e.g. 'P101')
                - The second one is the list of pointings, itself a dictionary
                  with a 0 or 1 for each pointing number depending on whether
                  this should be included in the reduction or not.
                  Results can be seen in self.dic_targets dictionary.
        rc_filename: str
            Default to None
        cal_filename: str
            Default to None

        PHANGS: bool
            Default to False. If True, will use default configuration dictionary
            from config_pipe.
        """
        self.sample = TargetDic
        self.targetnames = list(TargetDic.keys())

        self.first_recipe = first_recipe

        self.__phangs = kwargs.pop("PHANGS", False)
        self.verbose = kwargs.pop("verbose", False)

        # Reading configuration filenames
        if rc_filename is None or cal_filename is None:
            upipe.print_error("rc_filename and/or cal_filename is None. Please define both.")
            return
        self.cal_filename = cal_filename
        self.rc_filename = rc_filename
        self.folder_config = folder_config

        # Initialisation of rc and cal files
        self._init_calib_files()

        # Initialisation of targets
        self.init_pipes = kwargs.pop("init_pipes", True)
        self. add_targetname = kwargs.pop("add_targetname", True)
        self._init_targets()

    def _init_calib_files(self):
        """Initialise the calibration files with the new
        name using the subfolders
        """
        # Getting the right input for rc and cal names
        folder_config, rc_filename, cal_filename = self._get_calib_filenames()
        # First read the root folder
        init_cal_params = InitMuseParameters(folder_config=folder_config,
                                             rc_filename=rc_filename,
                                             cal_filename=cal_filename,
                                             verbose=self.verbose)
        self.root_path = init_cal_params.root
        self._subfolders = np.unique([self.sample[targetname][0]
                                for targetname in self.targetnames])
        for subfolder in self._subfolders:
            update_calib_file(rc_filename, subfolder, folder_config=folder_config)
            update_calib_file(cal_filename, subfolder, folder_config=folder_config)

    def _get_calib_filenames(self, targetname=None):
        """Get calibration file names

        Input
        ----
        targetname: str

        Returns
        -------
        folder_name: str
        rcname: str
        calname: str
        """
        # using targetname or not
        if targetname is None:
            name_rc = self.rc_filename
            name_cal = self.cal_filename
        else:
            name_rc = insert_suffix(self.rc_filename, self.targets[targetname].subfolder)
            name_cal = insert_suffix(self.cal_filename, self.targets[targetname].subfolder)

        folder_config = self.folder_config

        # Checking the folders
        folder_rc, rc_filename_target = os.path.split(joinpath(folder_config, name_rc))
        folder_cal, cal_filename_target = os.path.split(joinpath(folder_config, name_cal))

        if rc_filename_target=="" or cal_filename_target=="":
            upipe.print_error("Missing a calibration name file")
            return

        if folder_rc == folder_cal:
            folder_config = folder_rc
        else:
            rc_filename_target = joinpath(folder_rc, rc_filename_target)
            cal_filename_target = joinpath(folder_cal, cal_filename_target)
            folder_config = ""

        return folder_config, rc_filename_target, cal_filename_target

    def _init_targets(self):
        """Initialise the targets using the dictionary
        Returning self.targets with the pointings to consider
        """
        self.targets = {}
        self.pipes = {}
        self.pipes_combine = {}
        self.pipes_mosaic = {}
        for targetname in self.targetnames:
            subfolder = self.sample[targetname][0]
            lpoints = self.sample[targetname][1]
            list_pointings = []
            for lp in lpoints:
                if lpoints[lp] == 1:
                    list_pointings.append(lp)
            # Defining the MusePipe for that target
            self.targets[targetname] = MusePipeTarget(targetname=targetname,
                                                      subfolder=subfolder,
                                                      list_pointings=list_pointings)
            # Shortcut to call the musepipe instance
            self.pipes[targetname] = self.targets[targetname].pipes

            folder_config, rc_filename, cal_filename = self._get_calib_filenames(targetname)
            self.targets[targetname].rc_filename = rc_filename
            self.targets[targetname].cal_filename = cal_filename
            self.targets[targetname].folder_config = folder_config

            init_params_target = InitMuseParameters(rc_filename=rc_filename,
                                                    cal_filename=cal_filename,
                                                    folder_config=folder_config,
                                                    verbose=self.verbose)
            self.targets[targetname].root_path = init_params_target.root
            self.targets[targetname].data_path = joinpath(init_params_target.root, targetname)
            self.pipes[targetname].root_path = init_params_target.root
            self.pipes[targetname].data_path = joinpath(init_params_target.root, targetname)

            init_comb_target = MusePointings(targetname=targetname,
                                             list_pointings=list_pointings,
                                             rc_filename=rc_filename,
                                             cal_filename=cal_filename,
                                             folder_config=folder_config,
                                             verbose=self.verbose)
            self.targets[targetname].combcubes_path = init_comb_target.paths.cubes

            if self.init_pipes:
                self.set_pipe_target(targetname)

    def _check_pointings(self, targetname, list_pointings):
        """Check if pointing is in the list of pointings
        Returns the list of pointings if ok. If not, return an empty list

        Input
        -----
        targetname: str
            name of the target
        list_pointings: list
            List of integer (pointings).

        Returns
        -------
        list_pointings: list
            Empty if input list of pointings is not fully in defined list.
        """
        # Info of the pointings and extracting the observing run for each pointing
        target_pointings = self.targets[targetname].list_pointings
        # if no list_pointings we just do them all
        if list_pointings == None:
            list_pointings = target_pointings
        else:
            if any([_ not in target_pointings for _ in list_pointings]) :
                upipe.print_error("ERROR: no pointing {0} for the given target".format(
                                    list_pointings))
                return []
        return list_pointings

    def _check_targetname(self, targetname):
        """Check if targetname is in list

        Input
        -----
        targetname: str

        Returns
        -------
        status: bool
            True if yes, False if no.
        """
        if targetname not in self.targetnames:
            upipe.print_error("ERROR: no Target named {name} in the defined sample".format(
                                name=targetname))
            return False
        else:
            return True

    def set_pipe_target(self, targetname=None, list_pointings=None, 
                        **kwargs):
        """Create the musepipe instance for that target and list of pointings

        Input
        -----
        targetname: str
            Name of the target
        list_pointings: list
            Pointing numbers. Default is None (meaning all pointings
            indicated in the dictonary will be reduced)
        config_args: dic
            Dictionary including extra configuration parameters to pass
            to MusePipe. This allows to define a global configuration.
            If self.__phangs is set to True, this is overwritten with the default
            PHANGS configuration parameters as provided in config_pipe.py.
        """
        verbose = kwargs.pop("verbose", self.verbose)
        # Check if targetname is valid
        if not self._check_targetname(targetname):
            return

        # Galaxy name
        upipe.print_info("=== Initialising MusePipe for Target {name} ===".format(name=targetname))

        # Check if pointings are valid
        list_pointings = self._check_pointings(targetname, list_pointings)
        if len(list_pointings) == 0:
            return

        # Get the filename and extension of log file
        log_filename, log_fileext = os.path.splitext(kwargs.pop("log_filename", 
                        "{0}_{1}.log".format(targetname, version_pack)))

        # Reading extra arguments from config dictionary
        if self.__phangs:
            config_args = PHANGS_reduc_config
            # Set overwrite to False to keep existing tables
            config_args['overwrite_astropy_table'] = False
        else:
            config_args = kwargs.pop("config_args", None)

        first_recipe = kwargs.pop("first_recipe", 1)
        last_recipe = kwargs.pop("last_recipe", None)

        # Over-writing the arguments in kwargs from config dictionary
        if config_args is not None:
            for attr in config_args:
                if attr not in kwargs:
                    kwargs[attr] = config_args[attr]

        # extracting the kwargs
        list_kwargs = ', '.join(['{}={!r}'.format(k, v) for k, v in kwargs.items()])

        # Config files
        rc_filename = self.targets[targetname].rc_filename
        cal_filename = self.targets[targetname].cal_filename
        folder_config = self.targets[targetname].folder_config

        # Loop on the pointings
        for pointing in list_pointings:
            upipe.print_info("Initialise Pipe for Target = {0:10s} / Pointing {1:02d} ".format(
                                 targetname, pointing))
            # New log file name with pointing included
            log_filename_pointing = "{0}_P{1:02d}{2}".format(
                                    log_filename, pointing, log_fileext)
            # Setting up the names of the output files
            python_command = ("mypipe = musepipe.MusePipe(targetname='{0}', "
                              "pointing={1}, folder_config='{2}', " 
                              "rc_filename='{3}', " "cal_filename='{4}', "
                              "log_filename='{5}', verbose={6}, "
                              "{7})".format(targetname, pointing, folder_config, 
                                  rc_filename, cal_filename, log_filename_pointing, 
                                  verbose, list_kwargs))

            # Creating the musepipe instance, using the shortcut
            self.pipes[targetname][pointing] = MusePipe(
                targetname=targetname, pointing=pointing,
                folder_config=folder_config, rc_filename=rc_filename,
                cal_filename=cal_filename, log_filename=log_filename_pointing,
                first_recipe=first_recipe, last_recipe=last_recipe,
                init_raw_table=False, verbose=verbose, **kwargs)

            # Saving the command
            self.pipes[targetname][pointing].history = python_command
            # Setting back verbose to True to make sure we have a full account
            self.pipes[targetname][pointing].verbose = True
            upipe.print_info(python_command, pipe=self)

        upipe.print_info("End of Pipe initialisation")
        self.pipes[targetname]._initialised = True

    def  _get_path_data(self, targetname, pointing):
        """Get the path for the data
        Parameters
        ----------
        targetname: str
            Name of the target
        pointing: int
            Number for the pointing

        Returns
        -------
        path_data

        """
        return self.pipes[targetname][pointing].paths.data

    def  _get_path_files(self, targetname, pointing, expotype="OBJECT"):
        """Get the path for the files of a certain expotype
        Parameters
        ----------
        targetname: str
            Name of the target
        pointing: int
            Number for the pointing

        Returns
        -------
        path_files

        """
        return self.pipes[targetname][pointing]._get_path_files(expotype)

    def reduce_all_targets(self, **kwargs):
        """Reduce all targets already initialised

        Input
        -----
        first_recipe: int or str
            One of the recipe to start with
        last_recipe: int or str
            One of the recipe to end with
        """
        for target in self.targets:
            upipe.print_info("=== Start Reduction of Target {name} ===".format(name=target))
            self.reduce_target(targetname=target, **kwargs)
            upipe.print_info("===  End  Reduction of Target {name} ===".format(name=target))

    def reduce_target_prealign(self, targetname=None, list_pointings=None, **kwargs):
        """Reduce target for all steps before pre-alignment (included)

        Input
        -----
        targetname: str
            Name of the target
        list_pointings: list
            Pointing numbers. Default is None (meaning all pointings
            indicated in the dictonary will be reduced)
        """
        self.reduce_target(targetname=targetname, list_pointings=list_pointings,
                last_recipe="prep_align", **kwargs)

    def reduce_target_postalign(self, targetname=None, list_pointings=None, **kwargs):
        """Reduce target for all steps after pre-alignment

        Input
        -----
        targetname: str
            Name of the target
        list_pointings: list
            Pointing numbers. Default is None (meaning all pointings
            indicated in the dictonary will be reduced)
        """
        self.reduce_target(targetname=targetname, list_pointings=list_pointings, 
                first_recipe="align_bypointing", **kwargs)

    def run_target_scipost_perexpo(self, targetname=None, list_pointings=None,
                                   folder_offset_table=None, offset_table_name=None,
                                   **kwargs):
        """Build the cube per exposure using a given WCS

        Args:
            targetname:
            list_pointings:
            **kwargs:

        Returns:

        """
        # Check if pointings are valid
        list_pointings = self._check_pointings(targetname, list_pointings)
        if len(list_pointings) == 0:
            return

        # WCS imposed by setting the reference
        add_targetname = kwargs.pop("add_targetname", self.add_targetname)
        prefix_all = kwargs.pop("prefix_all", "")
        if add_targetname:
            prefix_all = "{0}_{1}".format(targetname, prefix_all)
        save = kwargs.pop("save", 'cube')

        wcs_auto = kwargs.pop("wcs_auto", True)
        if not wcs_auto:
            name_wcs = kwargs.pop("name_wcs", None)

        # Fetch the default folder for the WCS files which is the folder
        # of the Combined cubes
#        self.init_combine(targetname=targetname, folder_offset_table=folder_offset_table,
#                          offset_table_name=offset_table_name)
#        default_comb_folder = self.pipes_combine[targetname].paths.cubes
        default_comb_folder = self.targets[targetname].combcubes_path
        # Now fetch the value set by the user
        folder_ref_wcs = kwargs.pop("folder_ref_wcs", default_comb_folder)
        if self.__phangs:
            filter_list = kwargs.pop("filter_list", default_short_PHANGS_filter_list)
        else:
            filter_list = kwargs.pop("filter_list", default_short_filter_list)

        # Running the scipost_perexpo for all pointings individually
        for pointing in list_pointings:
            if wcs_auto:
                cube_suffix = dic_products_scipost['cube'][0]
                if add_targetname:
                     cube_suffix = "{0}_{1}".format(targetname, cube_suffix)
                name_wcs = "{0}_P{1:02d}.fits".format(cube_suffix,
                                                      np.int(pointing))
            suffix = "_WCS_P{0:02d}".format(np.int(pointing))
            kwargs_pointing = {'ref_wcs': name_wcs,
                               'suffix': suffix,
                               'folder_ref_wcs': folder_ref_wcs,
                               'sof_filename': 'scipost_wcs',
                               'dir_products': default_comb_folder,
                               'offset_table_name': offset_table_name,
                               'folder_offset_table': folder_offset_table,
                               'offset_list': True,
                               'filter_list': filter_list,
                               'prefix_all': prefix_all,
                               'save': save}
            kwargs.update(kwargs_pointing)
            self.pipes[targetname][pointing].run_scipost_perexpo(**kwargs)

    def run_target_recipe(self, recipe_name, targetname=None,
                          list_pointings=None, **kwargs):
        """Run just one recipe on target

        Input
        -----
        recipe_name: str
        targetname: str
            Name of the target
        list_pointings: list
            Pointing numbers. Default is None (meaning all pointings
            indicated in the dictonary will be reduced)
        """
        # General print out
        upipe.print_info("---- Starting the Recipe {0} for Target={1} "
                         "----".format(recipe_name, targetname))

        kwargs_recipe = {}
        for key, default in zip(['fraction', 'skymethod', 'illum'],
                                [0.8, "model", True]):
            _ = kwargs.pop(key, default)
            kwargs_recipe[key] = default

        # some parameters which depend on the pointings for this recipe
        kwargs_per_pointing = kwargs.pop("kwargs_per_pointing", {})

        # Initialise the pipe if needed
        self.set_pipe_target(targetname=targetname, list_pointings=list_pointings,
                first_recipe=recipe_name, last_recipe=recipe_name, **kwargs)

        # Check if pointings are valid
        list_pointings = self._check_pointings(targetname, list_pointings)
        if len(list_pointings) == 0:
            return

        # Loop on the pointings
        for pointing in list_pointings:
            upipe.print_info("====== START - POINTING {0:2d} "
                             "======".format(pointing))
            param_recipes = {}
            if pointing in kwargs_per_pointing:
                param_recipes[recipe_name] = kwargs_per_pointing[pointing]

            # Initialise raw tables if not already done (takes some time)
            if not self.pipes[targetname][pointing]._raw_table_initialised:
                self.pipes[targetname][pointing].init_raw_table(overwrite=True)
            if self.__phangs:
                self.pipes[targetname][pointing].run_phangs_recipes(param_recipes=param_recipes,
                                                                    **kwargs_recipe)
            else:
                self.pipes[targetname][pointing].run_recipes(param_recipes=param_recipes,
                                                             **kwargs_recipe)
            upipe.print_info("====== END   - POINTING {0:2d} ======".format(pointing))

    def reduce_target(self, targetname=None, list_pointings=None, **kwargs):
        """Reduce one target for a list of pointings

        Input
        -----
        targetname: str
            Name of the target
        list_pointings: list
            Pointing numbers. Default is None (meaning all pointings
            indicated in the dictonary will be reduced)
        first_recipe: str or int [1]
        last_recipe: str or int [max of all recipes]
            Name or number of the first and last recipes to process
        """
        # General print out
        upipe.print_info("---- Starting the Data Reduction for Target={0} ----".format(
                            targetname))

        kwargs_recipe = {}
        for key, default in zip(['fraction', 'skymethod', 'illum'], [0.8, "model", True]):
            item = kwargs.pop(key, default)
            kwargs_recipe[key] = default

        # Initialise the pipe if needed
        if not self.pipes[targetname]._initialised  \
            or "first_recipe" in kwargs or "last_recipe" in kwargs:
            self.set_pipe_target(targetname=targetname, list_pointings=list_pointings, **kwargs)

        # Check if pointings are valid
        list_pointings = self._check_pointings(targetname, list_pointings)
        if len(list_pointings) == 0:
            return

        # Loop on the pointings
        for pointing in list_pointings:
            upipe.print_info("====== START - POINTING {0:2d} ======".format(pointing))
            # Initialise raw tables if not already done (takes some time)
            if not self.pipes[targetname][pointing]._raw_table_initialised:
                self.pipes[targetname][pointing].init_raw_table(overwrite=True)
            if self.__phangs:
                self.pipes[targetname][pointing].run_phangs_recipes(**kwargs_recipe)
            else:
                self.pipes[targetname][pointing].run_recipes(**kwargs_recipe)
            upipe.print_info("====== END   - POINTING {0:2d} ======".format(pointing))

    def rotate_pixtables_target(self, targetname=None, list_pointings=None,
                                folder_offset_table=None, offset_table_name=None,
                                fakemode=False, **kwargs):
        """Rotate all pixel table of a certain targetname and pointings
        """
        # General print out
        upipe.print_info("---- Starting the PIXTABLE ROTATION "
                         "for Target={0} ----".format(targetname))

        # Initialise the pipe if needed
        if not self.pipes[targetname]._initialised \
            or "first_recipe" in kwargs or "last_recipe" in kwargs:
            self.set_pipe_target(targetname=targetname,
                                 list_pointings=list_pointings, **kwargs)

        # Check if pointings are valid
        list_pointings = self._check_pointings(targetname, list_pointings)
        if len(list_pointings) == 0:
            return

        # add_targetname = kwargs.pop("add_targetname", self.add_targetname)
        prefix = kwargs.pop("prefix", "")
        # if add_targetname:
        #     prefix = "{}_{}".format(targetname, prefix)
        if folder_offset_table is None:
            folder_offset_table = self.pipes[targetname][list_pointings[0]].paths.alignment
        offset_table = Table.read(joinpath(folder_offset_table, offset_table_name))
        offset_table.sort(["POINTING_OBS", "IEXPO_OBS"])
        # Loop on the pointings

        for row in offset_table:
            iexpo = row['IEXPO_OBS']
            pointing = row['POINTING_OBS']
            tpls = row['TPL_START']
            angle = row['ROTANGLE']
            upipe.print_info("Rotation ={0} Deg for Pointing={1:02d}, "
                             "TPLS={2} - Expo {3:02d}".format(
                                angle, pointing, tpls, iexpo))
            folder_expos = self._get_path_files(targetname, pointing)
            name_suffix = "{0}_{1:04d}".format(tpls, iexpo)
            rotate_pixtables(folder=folder_expos, name_suffix=name_suffix,
                             list_ifu=None, angle=angle, fakemode=fakemode,
                             prefix=prefix, **kwargs)

    def init_mosaic(self, targetname=None, list_pointings="all", **kwargs):
        """Prepare the combination of targets

        Input
        -----
        targetname: str [None]
            Name of target
        list_pointings: list [or "all"=default]
            List of pointings (e.g., [1,2,3])
        """
        # Check if pointings are valid
        list_pointings = self._check_pointings(targetname, list_pointings)
        if len(list_pointings) == 0:
            return

        # Make a list for the masking of the cubes to take into account
        list_pointing_names = ["P{0:02d}".format(np.int(pointing))
                               for pointing in list_pointings]

        folder_ref_wcs = kwargs.pop("folder_ref_wcs", comb_folder)
        self.pipes_mosaic[targetname] = MuseCubeMosaic(output_wcs=...,
                                                       folder_cubes=...,
                                                       prefix_cubes="DATACUBE_FINAL_WCS",
                                                       list_suffix=list_pointing_names)

    def mosaic(self, targetname=None, list_pointings="all", **kwargs):

        self.init_mosaic(targetname=targetname, list_pointings=list_pointings,
                         **kwargs)

        # Doing the mosaic with mad
        self.pipes_mosaic[targetname].madcombine()
        # Constructing the images for that mosaic
        if self.__phangs:
            filter_list = kwargs.pop("filter_list", default_PHANGS_filter_list)
        else:
            filter_list = kwargs.pop("filter_list", default_filter_list)

    def init_combine(self, targetname=None, list_pointings="all",
                     folder_offset_table=None, offset_table_name=None, **kwargs):
        """Prepare the combination of targets

        Input
        -----
        targetname: str [None]
            Name of target
        list_pointings: list [or "all"=default]
            List of pointings (e.g., [1,2,3])
        offset_table_name: str
            Name of Offset table
        """
        log_filename = kwargs.pop("log_filename", "{0}_combine_{1}.log".format(targetname, version_pack))
        self.pipes_combine[targetname] = MusePointings(targetname=targetname,
                                                 list_pointings=list_pointings,
                                                 rc_filename=self.targets[targetname].rc_filename,
                                                 cal_filename=self.targets[targetname].cal_filename,
                                                 folder_config=self.targets[targetname].folder_config,
                                                 offset_table_name=offset_table_name,
                                                 folder_offset_table=folder_offset_table,
                                                 log_filename=log_filename, **kwargs)

    def combine_target(self, targetname=None, **kwargs):
        """Run the combine recipe. Shortcut for combine[targetname].run_combine()
        """
        self.init_combine(targetname=targetname, **kwargs)
        self.pipes_combine[targetname].run_combine()

    def combine_target_pointings_withmasks(self, targetname=None, 
            combine=True, masks=True, perpointing_combine=True, mosaic_wcs=True,
            **kwargs):
        """Run the combine for individual exposures first building up
        a mask.
        """
        self.init_combine(targetname=targetname, **kwargs)
        self.pipes_combine[targetname].run_combine_all_single_pointings_withmasks(
            combine=combine, masks=masks, perpointing_combine=perpointing_combine,
            mosaic_wcs=mosaic_wcs, **kwargs)
