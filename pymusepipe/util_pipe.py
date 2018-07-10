# Licensed under a 3-clause BSD style license - see LICENSE.rst

"""MUSE-PHANGS utility functions for pymusepipe
"""

__authors__   = "Eric Emsellem"
__copyright__ = "(c) 2017, ESO + CRAL"
__license__   = "3-clause BSD License"
__contact__   = " <eric.emsellem@eso.org>"

# Importing modules
import os
import time

# Numpy
import numpy as np

from astropy import constants as const

# Import package modules
from pymusepipe.emission_lines import list_emission_lines

############    PRINTING FUNCTIONS #########################
HEADER = '\033[95m'
OKBLUE = '\033[94m'
OKGREEN = '\033[92m'
WARNING = '\033[1;31;20m'
INFO = '\033[1;32;20m'
ERROR = '\033[91m'
ENDC = '\033[0m'
BOLD = "\033[1m"
def print_endline(text, **kwargs) :
    print(INFO + text + ENDC, **kwargs)

def print_warning(text, **kwargs) :
    print(WARNING + "# MusePipeWarning " + ENDC + text, **kwargs)

def print_info(text, **kwargs) :
    print(INFO + "# MusePipeInfo " + ENDC + text, **kwargs)

def print_error(text, **kwargs) :
    print(ERROR + "# MusePipeError " + ENDC + text, **kwargs)
#-----------  END PRINTING FUNCTIONS -----------------------

def lower_allbutfirst_letter(mystring):
    """Lowercase all letters except the first one
    """
    return mystring[0].upper() + mystring[1:].lower()

def create_time_name() :
    """Create a time-link name for file saving purposes

    Return: a string including the YearMonthDay_HourMinSec
    """
    return str(time.strftime("%Y%m%d_%H%M%S", time.localtime()))

def formatted_time() :
    """ Return: a string including the formatted time
    """
    return str(time.strftime("%d-%m-%Y %H:%M:%S", time.localtime()))

# def get_date_inD(indate) :
#     """Transform date in Y-M-D
#     """
#     return np.datetime64(indate).astype('datetime64[D]')

def safely_create_folder(path, verbose=True):
    """Create a folder given by the input path
    This small function tries to create it and if it fails
    it checks whether the reason is because it is not a path
    and then warn the user
    and then warn the user
    """
    if path is None :
        if verbose : print_info("Input path is None, not doing anything")
        return
    if verbose : 
        print_info("Trying to create {folder} folder".format(folder=path), end='')
    try: 
        os.makedirs(path)
        print_endline("... Done", end='\n')
    except OSError:
        if not os.path.isdir(path):
            print_error("Failed to create folder! Please check the path")
            raise
            return
        if os.path.isdir(path):
            print_endline("... Folder already exists, doing nothing.")

def append_file(filename, content):
    """Append in ascii file
    """
    with open(filename, "a") as myfile:
        myfile.write(content)
        
def normpath(path) :
    """Normalise the path to get it short
    """
    return os.path.relpath(os.path.realpath(path))

# def overwrite_file(filename, content):
#     """Overwite in ascii file
#     """
#     with open(filename, "w+") as myfile:
#         myfile.write(content)

def doppler_shift(wavelength, velocity=0.):
    """Return the redshifted wavelength
    """
    doppler_factor = np.sqrt((1. + velocity / const.c.value) / (1. - velocity / const.c.value))
    return wavelength * doppler_factor

def get_emissionline_wavelength(line="Ha", velocity=0., redshift=None, medium='air'):
    """Get the wavelength of an emission line, including a correction
    for the redshift (or velocity)
    """
    index_line = {'vacuum': 0, 'air': 1}
    # Get the velocity
    if redshift is not None : velocity = redshift * const.c

    if line not in list_emission_lines.keys() :
        upipe.print_error("Could not guess the emission line you wish to use")
        upipe.print_error("Please review the 'emission_line' dictionary")
        return -1.

    if medium not in index_line.keys() :
        upipe.print_error("Please choose between one of these media: {0}".format(index_line.key()))
        return -1.

    wavel = list_emission_lines[line][index_line[medium]]
    return doppler_shift(wavel, velocity)

def get_emissionline_band(line="Ha", velocity=0., redshift=None, medium='air', window=10.0):
    """Get the wavelengths of an emission line, including a correction
    for the redshift (or velocity) and a window around that line (in Angstroems)

    Parameters
    ----------
    line: name of the line (string). Default is 'Ha'
    velocity: shift in velocity (km/s)
    medium: 'air' or 'vacuum'
    window: window in Angstroem
    """
    red_wavel = get_emissionline_wavelength(line=line, velocity=velocity, redshift=redshift, medium=medium)
    if red_wavel < 0 :
        return [0., 0.]
    else:
        return [red_wavel - window/2., red_wavel + window/2.]