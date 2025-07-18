import importlib
import platform
import re
import warnings
from contextlib import contextmanager
from distutils import version
from unittest import mock  # noqa: F401

import numpy as np
import pytest
import xarray.testing
from numpy.testing import assert_array_equal  # noqa: F401
from pandas.testing import assert_frame_equal  # noqa: F401
from xarray.core import utils
from xarray.core.duck_array_ops import allclose_or_equiv  # noqa: F401
from xarray.core.indexing import ExplicitlyIndexed
from xarray.core.options import set_options
from xarray.testing import (  # noqa: F401
    assert_duckarray_allclose,
    assert_duckarray_equal,
)

# import mpl and change the backend before other mpl imports
try:
    import matplotlib as mpl

    # Order of imports is important here.
    # Using a different backend makes Travis CI work
    mpl.use('Agg')
except ImportError:
    pass


arm_xfail = pytest.mark.xfail(
    platform.machine() == 'aarch64' or 'arm' in platform.machine(),
    reason='expected failure on ARM',
)


def _importorskip(modname, minversion=None):
    try:
        mod = importlib.import_module(modname)
        has = True
        if minversion is not None:
            if LooseVersion(mod.__version__) < LooseVersion(minversion):
                raise ImportError('Minimum version not satisfied')
    except ImportError:
        has = False
    func = pytest.mark.skipif(not has, reason=f'requires {modname}')
    return has, func


def LooseVersion(vstring):
    # Our development version is something like '0.10.9+aac7bfc'
    # This function just ignored the git commit id.
    vstring = vstring.split('+')[0]
    return version.LooseVersion(vstring)


has_matplotlib, requires_matplotlib = _importorskip('matplotlib')
has_scipy, requires_scipy = _importorskip('scipy')
has_pydap, requires_pydap = _importorskip('pydap.client')
has_netCDF4, requires_netCDF4 = _importorskip('netCDF4')
has_h5netcdf, requires_h5netcdf = _importorskip('h5netcdf')
has_pynio, requires_pynio = _importorskip('Nio')
has_pseudonetcdf, requires_pseudonetcdf = _importorskip('PseudoNetCDF')
has_cftime, requires_cftime = _importorskip('cftime')
has_cftime_1_1_0, requires_cftime_1_1_0 = _importorskip('cftime', minversion='1.1.0.0')
has_dask, requires_dask = _importorskip('dask')
has_bottleneck, requires_bottleneck = _importorskip('bottleneck')
has_nc_time_axis, requires_nc_time_axis = _importorskip('nc_time_axis')
has_rasterio, requires_rasterio = _importorskip('rasterio')
has_zarr, requires_zarr = _importorskip('zarr')
has_iris, requires_iris = _importorskip('iris')
has_cfgrib, requires_cfgrib = _importorskip('cfgrib')
has_numbagg, requires_numbagg = _importorskip('numbagg')
has_seaborn, requires_seaborn = _importorskip('seaborn')
has_sparse, requires_sparse = _importorskip('sparse')
has_cartopy, requires_cartopy = _importorskip('cartopy')

# some special cases
has_scipy_or_netCDF4 = has_scipy or has_netCDF4
requires_scipy_or_netCDF4 = pytest.mark.skipif(
    not has_scipy_or_netCDF4, reason='requires scipy or netCDF4'
)

# change some global options for tests
set_options(warn_for_unclosed_files=True)

if has_dask:
    import dask

    dask.config.set(scheduler='single-threaded')

flaky = pytest.mark.flaky
network = pytest.mark.network


@contextmanager
def raises_regex(error, pattern):
    __tracebackhide__ = True
    with pytest.raises(error) as excinfo:
        yield
    message = str(excinfo.value)
    if not re.search(pattern, message):
        raise AssertionError(
            f'exception {excinfo.value!r} did not match pattern {pattern!r}'
        )


class UnexpectedDataAccess(Exception):
    pass


class InaccessibleArray(utils.NDArrayMixin, ExplicitlyIndexed):
    def __init__(self, array):
        self.array = array

    def __getitem__(self, key):
        raise UnexpectedDataAccess('Tried accessing data')


class ReturnItem:
    def __getitem__(self, key):
        return key


class IndexerMaker:
    def __init__(self, indexer_cls):
        self._indexer_cls = indexer_cls

    def __getitem__(self, key):
        if not isinstance(key, tuple):
            key = (key,)
        return self._indexer_cls(key)


def source_ndarray(array):
    """Given an ndarray, return the base object which holds its memory, or the
    object itself.
    """
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', 'DatetimeIndex.base')
        warnings.filterwarnings('ignore', 'TimedeltaIndex.base')
        base = getattr(array, 'base', np.asarray(array).base)
    if base is None:
        base = array
    return base


# Internal versions of xarray's test functions that validate additional
# invariants


def assert_equal(a, b):
    __tracebackhide__ = True
    xarray.testing.assert_equal(a, b)
    xarray.testing._assert_internal_invariants(a)
    xarray.testing._assert_internal_invariants(b)


def assert_identical(a, b):
    __tracebackhide__ = True
    xarray.testing.assert_identical(a, b)
    xarray.testing._assert_internal_invariants(a)
    xarray.testing._assert_internal_invariants(b)


def assert_allclose(a, b, **kwargs):
    __tracebackhide__ = True
    xarray.testing.assert_allclose(a, b, **kwargs)
    xarray.testing._assert_internal_invariants(a)
    xarray.testing._assert_internal_invariants(b)
