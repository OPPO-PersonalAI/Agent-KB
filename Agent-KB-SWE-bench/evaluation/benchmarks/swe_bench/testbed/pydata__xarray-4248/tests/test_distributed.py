"""isort:skip_file"""

import pickle

import pytest

dask = pytest.importorskip('dask')  # isort:skip
distributed = pytest.importorskip('distributed')  # isort:skip

import xarray as xr
from dask.distributed import Client, Lock
from distributed.client import futures_of
from distributed.utils_test import cluster, gen_cluster, loop
from xarray.backends.locks import HDF5_LOCK, CombinedLock
from xarray.tests.test_backends import (
    ON_WINDOWS,
    create_tmp_file,
    create_tmp_geotiff,
    open_example_dataset,
)
from xarray.tests.test_dataset import create_test_data

from . import (
    assert_allclose,
    has_h5netcdf,
    has_netCDF4,
    has_scipy,
    requires_cfgrib,
    requires_rasterio,
    requires_zarr,
)

# this is to stop isort throwing errors. May have been easier to just use
# `isort:skip` in retrospect


da = pytest.importorskip('dask.array')
loop = loop  # loop is an imported fixture, which flake8 has issues ack-ing


@pytest.fixture
def tmp_netcdf_filename(tmpdir):
    return str(tmpdir.join('testfile.nc'))


ENGINES = []
if has_scipy:
    ENGINES.append('scipy')
if has_netCDF4:
    ENGINES.append('netcdf4')
if has_h5netcdf:
    ENGINES.append('h5netcdf')

NC_FORMATS = {
    'netcdf4': [
        'NETCDF3_CLASSIC',
        'NETCDF3_64BIT_OFFSET',
        'NETCDF3_64BIT_DATA',
        'NETCDF4_CLASSIC',
        'NETCDF4',
    ],
    'scipy': ['NETCDF3_CLASSIC', 'NETCDF3_64BIT'],
    'h5netcdf': ['NETCDF4'],
}

ENGINES_AND_FORMATS = [
    ('netcdf4', 'NETCDF3_CLASSIC'),
    ('netcdf4', 'NETCDF4_CLASSIC'),
    ('netcdf4', 'NETCDF4'),
    ('h5netcdf', 'NETCDF4'),
    ('scipy', 'NETCDF3_64BIT'),
]


@pytest.mark.parametrize('engine,nc_format', ENGINES_AND_FORMATS)
def test_dask_distributed_netcdf_roundtrip(
    loop, tmp_netcdf_filename, engine, nc_format
):
    if engine not in ENGINES:
        pytest.skip('engine not available')

    chunks = {'dim1': 4, 'dim2': 3, 'dim3': 6}

    with cluster() as (s, [a, b]):
        with Client(s['address'], loop=loop):
            original = create_test_data().chunk(chunks)

            if engine == 'scipy':
                with pytest.raises(NotImplementedError):
                    original.to_netcdf(
                        tmp_netcdf_filename, engine=engine, format=nc_format
                    )
                return

            original.to_netcdf(tmp_netcdf_filename, engine=engine, format=nc_format)

            with xr.open_dataset(
                tmp_netcdf_filename, chunks=chunks, engine=engine
            ) as restored:
                assert isinstance(restored.var1.data, da.Array)
                computed = restored.compute()
                assert_allclose(original, computed)


@pytest.mark.parametrize('engine,nc_format', ENGINES_AND_FORMATS)
def test_dask_distributed_read_netcdf_integration_test(
    loop, tmp_netcdf_filename, engine, nc_format
):
    if engine not in ENGINES:
        pytest.skip('engine not available')

    chunks = {'dim1': 4, 'dim2': 3, 'dim3': 6}

    with cluster() as (s, [a, b]):
        with Client(s['address'], loop=loop):
            original = create_test_data()
            original.to_netcdf(tmp_netcdf_filename, engine=engine, format=nc_format)

            with xr.open_dataset(
                tmp_netcdf_filename, chunks=chunks, engine=engine
            ) as restored:
                assert isinstance(restored.var1.data, da.Array)
                computed = restored.compute()
                assert_allclose(original, computed)


@requires_zarr
@pytest.mark.parametrize('consolidated', [True, False])
@pytest.mark.parametrize('compute', [True, False])
def test_dask_distributed_zarr_integration_test(loop, consolidated, compute):
    if consolidated:
        pytest.importorskip('zarr', minversion='2.2.1.dev2')
        write_kwargs = dict(consolidated=True)
        read_kwargs = dict(consolidated=True)
    else:
        write_kwargs = read_kwargs = {}
    chunks = {'dim1': 4, 'dim2': 3, 'dim3': 5}
    with cluster() as (s, [a, b]):
        with Client(s['address'], loop=loop):
            original = create_test_data().chunk(chunks)
            with create_tmp_file(
                allow_cleanup_failure=ON_WINDOWS, suffix='.zarrc'
            ) as filename:
                maybe_futures = original.to_zarr(
                    filename, compute=compute, **write_kwargs
                )
                if not compute:
                    maybe_futures.compute()
                with xr.open_zarr(filename, **read_kwargs) as restored:
                    assert isinstance(restored.var1.data, da.Array)
                    computed = restored.compute()
                    assert_allclose(original, computed)


@requires_rasterio
def test_dask_distributed_rasterio_integration_test(loop):
    with create_tmp_geotiff() as (tmp_file, expected):
        with cluster() as (s, [a, b]):
            with Client(s['address'], loop=loop):
                da_tiff = xr.open_rasterio(tmp_file, chunks={'band': 1})
                assert isinstance(da_tiff.data, da.Array)
                actual = da_tiff.compute()
                assert_allclose(actual, expected)


@requires_cfgrib
def test_dask_distributed_cfgrib_integration_test(loop):
    with cluster() as (s, [a, b]):
        with Client(s['address'], loop=loop):
            with open_example_dataset(
                'example.grib', engine='cfgrib', chunks={'time': 1}
            ) as ds:
                with open_example_dataset('example.grib', engine='cfgrib') as expected:
                    assert isinstance(ds['t'].data, da.Array)
                    actual = ds.compute()
                    assert_allclose(actual, expected)


@pytest.mark.skipif(
    distributed.__version__ <= '1.19.3',
    reason='Need recent distributed version to clean up get',
)
@gen_cluster(client=True, timeout=None)
async def test_async(c, s, a, b):
    x = create_test_data()
    assert not dask.is_dask_collection(x)
    y = x.chunk({'dim2': 4}) + 10
    assert dask.is_dask_collection(y)
    assert dask.is_dask_collection(y.var1)
    assert dask.is_dask_collection(y.var2)

    z = y.persist()
    assert str(z)

    assert dask.is_dask_collection(z)
    assert dask.is_dask_collection(z.var1)
    assert dask.is_dask_collection(z.var2)
    assert len(y.__dask_graph__()) > len(z.__dask_graph__())

    assert not futures_of(y)
    assert futures_of(z)

    future = c.compute(z)
    w = await future
    assert not dask.is_dask_collection(w)
    assert_allclose(x + 10, w)

    assert s.tasks


def test_hdf5_lock():
    assert isinstance(HDF5_LOCK, dask.utils.SerializableLock)


@gen_cluster(client=True)
async def test_serializable_locks(c, s, a, b):
    def f(x, lock=None):
        with lock:
            return x + 1

    # note, the creation of Lock needs to be done inside a cluster
    for lock in [
        HDF5_LOCK,
        Lock(),
        Lock('filename.nc'),
        CombinedLock([HDF5_LOCK]),
        CombinedLock([HDF5_LOCK, Lock('filename.nc')]),
    ]:
        futures = c.map(f, list(range(10)), lock=lock)
        await c.gather(futures)

        lock2 = pickle.loads(pickle.dumps(lock))
        assert type(lock) == type(lock2)
