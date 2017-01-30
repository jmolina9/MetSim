"""
MTCLIM
"""

import numpy as np
import pandas as pd
from warnings import warn

import metsim.constants as cnst
from metsim.disaggregate import disaggregate
from metsim.physics import svp, calc_pet, atm_pres, solar_geom

def run(forcing: pd.DataFrame, params: dict, disagg=True):
    """ 
    Run all of the mtclim forcing generation 
    
    Args:
        forcing: The daily forcings given from input
        solar_geom: Solar geometry of the site
    """   
    lat_idx = forcing.index.names.index('lat')
    time_idx = forcing.index.names.index('time')

    # solar_geom returns a tuple due to restrictions of numba
    # for clarity we convert it to a dataframe here
    sg = solar_geom(forcing['elev'][0], forcing.index.levels[lat_idx][0])
    sg = {'tiny_rad_fract' : sg[0],
          'daylength' : sg[1],
          'potrad' : sg[2],
          'tt_max0' : sg[3]}
    forcing.index = forcing.index.levels[time_idx]
    params['n_days'] = len(forcing.index)
    calc_t_air(forcing, params)
    calc_precip(forcing, params)
    calc_snowpack(forcing, params)
    calc_srad_hum(forcing, sg, params)
    
    if disagg:
        forcing = disaggregate(forcing, params, sg)

    return forcing


def calc_t_air(df: pd.DataFrame, params: dict):
    """ 
    Adjust temperatures according to lapse rates 
    and calculate t_day
    """
    dZ = (df['elev'][0] - params['base_elev'])/1000.
    lapse_rates = [params['t_min_lr'], params['t_max_lr']]
    t_max = df['t_max'] + dZ * lapse_rates[1]
    t_min = df['t_min'].where(df['t_min'] + dZ * lapse_rates[0] < t_max-0.5, t_max-0.5)
    t_mean = (t_min + t_max)/2
    df['t_day'] = ((t_max - t_mean) * cnst.TDAY_COEF) + t_mean


def calc_precip(df: pd.DataFrame, params: dict):
    """ Adjust precipitation according to isoh """
    df['precip'] = (df['precip'] * (df.get('site_isoh', 1) / df.get('base_isoh', 1)))


def calc_snowpack(df: pd.DataFrame, params: dict, snowpack=0.0):
    """Calculate snowpack as swe."""
    swe = pd.Series(snowpack, index=df.index)
    accum = (df['t_min'] <= cnst.SNOW_TCRIT)
    melt = (df['t_min'] >  cnst.SNOW_TCRIT)
    swe[accum] += df['precip'][accum]
    swe[melt] -= cnst.SNOW_TRATE * (df['t_min'][melt] - cnst.SNOW_TCRIT)
    df['swe'] = np.maximum(np.cumsum(swe), 0.0) 


def calc_srad_hum(df: pd.DataFrame, sg: dict, params: dict, win_type='boxcar'):
    """Calculate shortwave, humidity"""

    def _calc_tfmax(precip, dtr, sm_dtr):
        b = cnst.B0 + cnst.B1 * np.exp(-cnst.B2 * sm_dtr)
        t_fmax = 1.0 - 0.9 * np.exp(-b * np.power(dtr, cnst.C))
        inds = np.array(precip > cnst.SW_PREC_THRESH)
        t_fmax[inds] *= cnst.RAIN_SCALAR
        return t_fmax 

    # Calculate the diurnal temperature range
    df['t_max'] = np.maximum(df['t_max'], df['t_min'])
    dtr = df['t_max'] - df['t_min']
    sm_dtr = pd.Series(dtr).rolling(window=30, win_type=win_type,
                axis=0).mean().fillna(method='bfill')
    if params['n_days'] <= 30:
        warn('Timeseries is shorter than rolling mean window, filling ')
        warn('missing values with unsmoothed data')
        sm_dtr.fillna(dtr, inplace=True)

    # Calculate annual total precip
    sum_precip = df['precip'].values.sum()
    ann_precip = (sum_precip / params['n_days']) * cnst.DAYS_PER_YEAR
    if ann_precip == 0.0:
        ann_precip = 1.0

    # Effective annual precip
    if params['n_days'] <= 90:
        # Simple scaled method, minimum of 8 cm 
        sum_precip = df['precip'].values.sum()
        eff_ann_precip = (sum_precip / params['n_days']) * cnst.DAYS_PER_YEAR
        eff_ann_precip = np.maximum(eff_ann_precip, 8.0)
        parray = eff_ann_precip
    else:
        # Calculate effective annual precip using 3 month moving window
        window = pd.Series(np.zeros(params['n_days'] + 90))
        window[90:] = df['precip']
        
        # If yeardays at end match with those at beginning we can use
        # the end of the input to generate the beginning by looping around
        # If not, just duplicate the first 90 days
        start_day, end_day = df['day_of_year'][0], df['day_of_year'][-1]
        if (start_day%365 == (end_day%365)+1) or (start_day%366 == (end_day%366)+1):
            window[:90] = df['precip'][-90:]
        else:
            window[:90] = df['precip'][:90]

        parray = (window.rolling(window=90, win_type=win_type, axis=0) 
                    .mean()[90:] * cnst.DAYS_PER_YEAR)

    # Convert to mm 
    parray = parray.where(parray>80.0, 80.0) * cnst.CM_TO_MM
    # Doing this way because parray.reindex_like(df) returns all nan
    parray.index = df.index 
    df['tfmax'] = _calc_tfmax(df['precip'], dtr, sm_dtr) 
    tdew = df.get('tdew', df['t_min'])
    pva = df.get('hum', svp(tdew))
    pa = atm_pres(df['elev'][0])
    yday = df['day_of_year'] - 1 
    df['dayl'] = sg['daylength'][yday]
 
    # Calculation of tdew and swrad. tdew is iterated on until
    # it converges sufficiently 
    tdew_old = tdew
    tdew, pva = sw_hum_iter(df, sg, pa, pva, parray, dtr)
    while(np.sqrt(np.mean((tdew-tdew_old)**2)) > 1e-3):
        tdew_old = np.copy(tdew)
        tdew, pva = sw_hum_iter(df, sg, pa, pva, parray, dtr)
    df['vapor_pressure'] = pva 


def sw_hum_iter(df, sg, pa, pva, parray, dtr):
    tt_max0 = sg['tt_max0']
    potrad = sg['potrad']
    daylength = sg['daylength']
    yday = df['day_of_year'] - 1

    t_tmax = np.maximum(tt_max0[yday] + (cnst.ABASE * pva), 0.0001)
    t_final = t_tmax * df['tfmax']

    # Snowpack contribution 
    sc = np.zeros_like(df['swe'])
    if (cnst.MTCLIM_SWE_CORR):
        inds = np.logical_and(df['swe'] > 0.,  daylength[yday] > 0.)
        sc[inds] = (1.32 + 0.096 * df['swe'][inds]) * 1.0e6 / daylength[yday][inds]
        sc = np.maximum(sc, 100.)  # JJH - this is fishy 

    # Calculation of shortwave is split into 2 components:
    # 1. Radiation from incident light
    # 2. Influence of snowpack - optionally set by MTCLIM_SWE_CORR
    df['swrad'] = potrad[yday] * t_final + sc

    # Calculate cloud effect
    if (cnst.LW_CLOUD.upper() == 'CLOUD_DEARDORFF'):
        df['tskc'] = (1. - df['tfmax'])
    else:
        df['tskc'] = np.sqrt((1. - df['tfmax']) / 0.65)

    # Compute PET using SW radiation estimate, and update Tdew, pva **
    pet = calc_pet(df['swrad'], df['t_day'], pa, df['dayl'])
    # Calculate ratio (PET/effann_prcp) and correct the dewpoint
    ratio = pet / parray
    df['pet'] = parray 
    tmink = df['t_min'] + cnst.KELVIN
    tdew = tmink*(-0.127 + 1.121*(1.003 - 1.444*ratio + 12.312*np.power(ratio, 2)  
            - 32.766*np.power(ratio, 3)) + 0.0006*dtr) - cnst.KELVIN
    return tdew, svp(tdew)


