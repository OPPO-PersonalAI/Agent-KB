import datetime as dt
import warnings
from textwrap import dedent

import numpy as np
import pandas as pd
import pytest
from numpy import array, nan
from xarray import DataArray, Dataset, cftime_range, concat
from xarray.core import dtypes, duck_array_ops
from xarray.core.duck_array_ops import (
    array_notnull_equiv,
    concatenate,
    count,
    first,
    gradient,
    last,
    least_squares,
    mean,
    np_timedelta64_to_float,
    pd_timedelta_to_float,
    py_timedelta_to_float,
    rolling_window,
    stack,
    timedelta_to_numeric,
    where,
)
from xarray.core.pycompat import dask_array_type
from xarray.testing import assert_allclose, assert_equal

from . import (
    arm_xfail,
    assert_array_equal,
    has_dask,
    raises_regex,
    requires_cftime,
    requires_dask,
)


class TestOps:
    @pytest.fixture(autouse=True)
    def setUp(self):
        self.x = array(
            [
                [[nan, nan, 2.0, nan], [nan, 5.0, 6.0, nan], [8.0, 9.0, 10.0, nan]],
                [
                    [nan, 13.0, 14.0, 15.0],
                    [nan, 17.0, 18.0, nan],
                    [nan, 21.0, nan, nan],
                ],
            ]
        )

    def test_first(self):
        expected_results = [
            array([[nan, 13, 2, 15], [nan, 5, 6, nan], [8, 9, 10, nan]]),
            array([[8, 5, 2, nan], [nan, 13, 14, 15]]),
            array([[2, 5, 8], [13, 17, 21]]),
        ]
        for axis, expected in zip([0, 1, 2, -3, -2, -1], 2 * expected_results):
            actual = first(self.x, axis)
            assert_array_equal(expected, actual)

        expected = self.x[0]
        actual = first(self.x, axis=0, skipna=False)
        assert_array_equal(expected, actual)

        expected = self.x[..., 0]
        actual = first(self.x, axis=-1, skipna=False)
        assert_array_equal(expected, actual)

        with raises_regex(IndexError, 'out of bounds'):
            first(self.x, 3)

    def test_last(self):
        expected_results = [
            array([[nan, 13, 14, 15], [nan, 17, 18, nan], [8, 21, 10, nan]]),
            array([[8, 9, 10, nan], [nan, 21, 18, 15]]),
            array([[2, 6, 10], [15, 18, 21]]),
        ]
        for axis, expected in zip([0, 1, 2, -3, -2, -1], 2 * expected_results):
            actual = last(self.x, axis)
            assert_array_equal(expected, actual)

        expected = self.x[-1]
        actual = last(self.x, axis=0, skipna=False)
        assert_array_equal(expected, actual)

        expected = self.x[..., -1]
        actual = last(self.x, axis=-1, skipna=False)
        assert_array_equal(expected, actual)

        with raises_regex(IndexError, 'out of bounds'):
            last(self.x, 3)

    def test_count(self):
        assert 12 == count(self.x)

        expected = array([[1, 2, 3], [3, 2, 1]])
        assert_array_equal(expected, count(self.x, axis=-1))

        assert 1 == count(np.datetime64('2000-01-01'))

    def test_where_type_promotion(self):
        result = where([True, False], [1, 2], ['a', 'b'])
        assert_array_equal(result, np.array([1, 'b'], dtype=object))

        result = where([True, False], np.array([1, 2], np.float32), np.nan)
        assert result.dtype == np.float32
        assert_array_equal(result, np.array([1, np.nan], dtype=np.float32))

    def test_stack_type_promotion(self):
        result = stack([1, 'b'])
        assert_array_equal(result, np.array([1, 'b'], dtype=object))

    def test_concatenate_type_promotion(self):
        result = concatenate([[1], ['b']])
        assert_array_equal(result, np.array([1, 'b'], dtype=object))

    def test_all_nan_arrays(self):
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', 'All-NaN slice')
            warnings.filterwarnings('ignore', 'Mean of empty slice')
            assert np.isnan(mean([np.nan, np.nan]))


def test_cumsum_1d():
    inputs = np.array([0, 1, 2, 3])
    expected = np.array([0, 1, 3, 6])
    actual = duck_array_ops.cumsum(inputs)
    assert_array_equal(expected, actual)

    actual = duck_array_ops.cumsum(inputs, axis=0)
    assert_array_equal(expected, actual)

    actual = duck_array_ops.cumsum(inputs, axis=-1)
    assert_array_equal(expected, actual)

    actual = duck_array_ops.cumsum(inputs, axis=(0,))
    assert_array_equal(expected, actual)

    actual = duck_array_ops.cumsum(inputs, axis=())
    assert_array_equal(inputs, actual)


def test_cumsum_2d():
    inputs = np.array([[1, 2], [3, 4]])

    expected = np.array([[1, 3], [4, 10]])
    actual = duck_array_ops.cumsum(inputs)
    assert_array_equal(expected, actual)

    actual = duck_array_ops.cumsum(inputs, axis=(0, 1))
    assert_array_equal(expected, actual)

    actual = duck_array_ops.cumsum(inputs, axis=())
    assert_array_equal(inputs, actual)


def test_cumprod_2d():
    inputs = np.array([[1, 2], [3, 4]])

    expected = np.array([[1, 2], [3, 2 * 3 * 4]])
    actual = duck_array_ops.cumprod(inputs)
    assert_array_equal(expected, actual)

    actual = duck_array_ops.cumprod(inputs, axis=(0, 1))
    assert_array_equal(expected, actual)

    actual = duck_array_ops.cumprod(inputs, axis=())
    assert_array_equal(inputs, actual)


class TestArrayNotNullEquiv:
    @pytest.mark.parametrize(
        'arr1, arr2',
        [
            (np.array([1, 2, 3]), np.array([1, 2, 3])),
            (np.array([1, 2, np.nan]), np.array([1, np.nan, 3])),
            (np.array([np.nan, 2, np.nan]), np.array([1, np.nan, np.nan])),
        ],
    )
    def test_equal(self, arr1, arr2):
        assert array_notnull_equiv(arr1, arr2)

    def test_some_not_equal(self):
        a = np.array([1, 2, 4])
        b = np.array([1, np.nan, 3])
        assert not array_notnull_equiv(a, b)

    def test_wrong_shape(self):
        a = np.array([[1, np.nan, np.nan, 4]])
        b = np.array([[1, 2], [np.nan, 4]])
        assert not array_notnull_equiv(a, b)

    @pytest.mark.parametrize(
        'val1, val2, val3, null',
        [
            (
                np.datetime64('2000'),
                np.datetime64('2001'),
                np.datetime64('2002'),
                np.datetime64('NaT'),
            ),
            (1.0, 2.0, 3.0, np.nan),
            ('foo', 'bar', 'baz', None),
            ('foo', 'bar', 'baz', np.nan),
        ],
    )
    def test_types(self, val1, val2, val3, null):
        dtype = object if isinstance(val1, str) else None
        arr1 = np.array([val1, null, val3, null], dtype=dtype)
        arr2 = np.array([val1, val2, null, null], dtype=dtype)
        assert array_notnull_equiv(arr1, arr2)


def construct_dataarray(dim_num, dtype, contains_nan, dask):
    # dimnum <= 3
    rng = np.random.RandomState(0)
    shapes = [16, 8, 4][:dim_num]
    dims = ('x', 'y', 'z')[:dim_num]

    if np.issubdtype(dtype, np.floating):
        array = rng.randn(*shapes).astype(dtype)
    elif np.issubdtype(dtype, np.integer):
        array = rng.randint(0, 10, size=shapes).astype(dtype)
    elif np.issubdtype(dtype, np.bool_):
        array = rng.randint(0, 1, size=shapes).astype(dtype)
    elif dtype == str:
        array = rng.choice(['a', 'b', 'c', 'd'], size=shapes)
    else:
        raise ValueError

    if contains_nan:
        inds = rng.choice(range(array.size), int(array.size * 0.2))
        dtype, fill_value = dtypes.maybe_promote(array.dtype)
        array = array.astype(dtype)
        array.flat[inds] = fill_value

    da = DataArray(array, dims=dims, coords={'x': np.arange(16)}, name='da')

    if dask and has_dask:
        chunks = {d: 4 for d in dims}
        da = da.chunk(chunks)

    return da


def from_series_or_scalar(se):
    if isinstance(se, pd.Series):
        return DataArray.from_series(se)
    else:  # scalar case
        return DataArray(se)


def series_reduce(da, func, dim, **kwargs):
    """convert DataArray to pd.Series, apply pd.func, then convert back to
    a DataArray. Multiple dims cannot be specified."""
    if dim is None or da.ndim == 1:
        se = da.to_series()
        return from_series_or_scalar(getattr(se, func)(**kwargs))
    else:
        da1 = []
        dims = list(da.dims)
        dims.remove(dim)
        d = dims[0]
        for i in range(len(da[d])):
            da1.append(series_reduce(da.isel(**{d: i}), func, dim, **kwargs))

        if d in da.coords:
            return concat(da1, dim=da[d])
        return concat(da1, dim=d)


def assert_dask_array(da, dask):
    if dask and da.ndim > 0:
        assert isinstance(da.data, dask_array_type)


@arm_xfail
@pytest.mark.filterwarnings('ignore::RuntimeWarning')
@pytest.mark.parametrize('dask', [False, True] if has_dask else [False])
def test_datetime_mean(dask):
    # Note: only testing numpy, as dask is broken upstream
    da = DataArray(
        np.array(['2010-01-01', 'NaT', '2010-01-03', 'NaT', 'NaT'], dtype='M8'),
        dims=['time'],
    )
    if dask:
        # Trigger use case where a chunk is full of NaT
        da = da.chunk({'time': 3})

    expect = DataArray(np.array('2010-01-02', dtype='M8'))
    expect_nat = DataArray(np.array('NaT', dtype='M8'))

    actual = da.mean()
    if dask:
        assert actual.chunks is not None
    assert_equal(actual, expect)

    actual = da.mean(skipna=False)
    if dask:
        assert actual.chunks is not None
    assert_equal(actual, expect_nat)

    # tests for 1d array full of NaT
    assert_equal(da[[1]].mean(), expect_nat)
    assert_equal(da[[1]].mean(skipna=False), expect_nat)

    # tests for a 0d array
    assert_equal(da[0].mean(), da[0])
    assert_equal(da[0].mean(skipna=False), da[0])
    assert_equal(da[1].mean(), expect_nat)
    assert_equal(da[1].mean(skipna=False), expect_nat)


@requires_cftime
def test_cftime_datetime_mean():
    times = cftime_range('2000', periods=4)
    da = DataArray(times, dims=['time'])

    assert da.isel(time=0).mean() == da.isel(time=0)

    expected = DataArray(times.date_type(2000, 1, 2, 12))
    result = da.mean()
    assert_equal(result, expected)

    da_2d = DataArray(times.values.reshape(2, 2))
    result = da_2d.mean()
    assert_equal(result, expected)


@requires_cftime
@requires_dask
def test_cftime_datetime_mean_dask_error():
    times = cftime_range('2000', periods=4)
    da = DataArray(times, dims=['time']).chunk()
    with pytest.raises(NotImplementedError):
        da.mean()


@pytest.mark.parametrize('dim_num', [1, 2])
@pytest.mark.parametrize('dtype', [float, int, np.float32, np.bool_])
@pytest.mark.parametrize('dask', [False, True])
@pytest.mark.parametrize('func', ['sum', 'min', 'max', 'mean', 'var'])
# TODO test cumsum, cumprod
@pytest.mark.parametrize('skipna', [False, True])
@pytest.mark.parametrize('aggdim', [None, 'x'])
def test_reduce(dim_num, dtype, dask, func, skipna, aggdim):
    if aggdim == 'y' and dim_num < 2:
        pytest.skip('dim not in this test')

    if dtype == np.bool_ and func == 'mean':
        pytest.skip('numpy does not support this')

    if dask and not has_dask:
        pytest.skip('requires dask')

    if dask and skipna is False and dtype in [np.bool_]:
        pytest.skip('dask does not compute object-typed array')

    rtol = 1e-04 if dtype == np.float32 else 1e-05

    da = construct_dataarray(dim_num, dtype, contains_nan=True, dask=dask)
    axis = None if aggdim is None else da.get_axis_num(aggdim)

    # TODO: remove these after resolving
    # https://github.com/dask/dask/issues/3245
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', 'Mean of empty slice')
        warnings.filterwarnings('ignore', 'All-NaN slice')
        warnings.filterwarnings('ignore', 'invalid value encountered in')

        if da.dtype.kind == 'O' and skipna:
            # Numpy < 1.13 does not handle object-type array.
            try:
                if skipna:
                    expected = getattr(np, f'nan{func}')(da.values, axis=axis)
                else:
                    expected = getattr(np, func)(da.values, axis=axis)

                actual = getattr(da, func)(skipna=skipna, dim=aggdim)
                assert_dask_array(actual, dask)
                np.testing.assert_allclose(
                    actual.values, np.array(expected), rtol=1.0e-4, equal_nan=True
                )
            except (TypeError, AttributeError, ZeroDivisionError):
                # TODO currently, numpy does not support some methods such as
                # nanmean for object dtype
                pass

        actual = getattr(da, func)(skipna=skipna, dim=aggdim)

        # for dask case, make sure the result is the same for numpy backend
        expected = getattr(da.compute(), func)(skipna=skipna, dim=aggdim)
        assert_allclose(actual, expected, rtol=rtol)

        # make sure the compatiblility with pandas' results.
        if func in ['var', 'std']:
            expected = series_reduce(da, func, skipna=skipna, dim=aggdim, ddof=0)
            assert_allclose(actual, expected, rtol=rtol)
            # also check ddof!=0 case
            actual = getattr(da, func)(skipna=skipna, dim=aggdim, ddof=5)
            if dask:
                assert isinstance(da.data, dask_array_type)
            expected = series_reduce(da, func, skipna=skipna, dim=aggdim, ddof=5)
            assert_allclose(actual, expected, rtol=rtol)
        else:
            expected = series_reduce(da, func, skipna=skipna, dim=aggdim)
            assert_allclose(actual, expected, rtol=rtol)

        # make sure the dtype argument
        if func not in ['max', 'min']:
            actual = getattr(da, func)(skipna=skipna, dim=aggdim, dtype=float)
            assert_dask_array(actual, dask)
            assert actual.dtype == float

        # without nan
        da = construct_dataarray(dim_num, dtype, contains_nan=False, dask=dask)
        actual = getattr(da, func)(skipna=skipna)
        if dask:
            assert isinstance(da.data, dask_array_type)
        expected = getattr(np, f'nan{func}')(da.values)
        if actual.dtype == object:
            assert actual.values == np.array(expected)
        else:
            assert np.allclose(actual.values, np.array(expected), rtol=rtol)


@pytest.mark.parametrize('dim_num', [1, 2])
@pytest.mark.parametrize('dtype', [float, int, np.float32, np.bool_, str])
@pytest.mark.parametrize('contains_nan', [True, False])
@pytest.mark.parametrize('dask', [False, True])
@pytest.mark.parametrize('func', ['min', 'max'])
@pytest.mark.parametrize('skipna', [False, True])
@pytest.mark.parametrize('aggdim', ['x', 'y'])
def test_argmin_max(dim_num, dtype, contains_nan, dask, func, skipna, aggdim):
    # pandas-dev/pandas#16830, we do not check consistency with pandas but
    # just make sure da[da.argmin()] == da.min()

    if aggdim == 'y' and dim_num < 2:
        pytest.skip('dim not in this test')

    if dask and not has_dask:
        pytest.skip('requires dask')

    if contains_nan:
        if not skipna:
            pytest.skip(
                "numpy's argmin (not nanargmin) does not handle " 'object-dtype'
            )
        if skipna and np.dtype(dtype).kind in 'iufc':
            pytest.skip("numpy's nanargmin raises ValueError for all nan axis")
    da = construct_dataarray(dim_num, dtype, contains_nan=contains_nan, dask=dask)

    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', 'All-NaN slice')

        actual = da.isel(
            **{aggdim: getattr(da, 'arg' + func)(dim=aggdim, skipna=skipna).compute()}
        )
        expected = getattr(da, func)(dim=aggdim, skipna=skipna)
        assert_allclose(
            actual.drop_vars(list(actual.coords)),
            expected.drop_vars(list(expected.coords)),
        )


def test_argmin_max_error():
    da = construct_dataarray(2, np.bool_, contains_nan=True, dask=False)
    da[0] = np.nan
    with pytest.raises(ValueError):
        da.argmin(dim='y')


@pytest.mark.parametrize(
    'array',
    [
        np.array([np.datetime64('2000-01-01'), np.datetime64('NaT')]),
        np.array([np.timedelta64(1, 'h'), np.timedelta64('NaT')]),
        np.array([0.0, np.nan]),
        np.array([1j, np.nan]),
        np.array(['foo', np.nan], dtype=object),
    ],
)
def test_isnull(array):
    expected = np.array([False, True])
    actual = duck_array_ops.isnull(array)
    np.testing.assert_equal(expected, actual)


@requires_dask
def test_isnull_with_dask():
    da = construct_dataarray(2, np.float32, contains_nan=True, dask=True)
    assert isinstance(da.isnull().data, dask_array_type)
    assert_equal(da.isnull().load(), da.load().isnull())


@pytest.mark.skipif(not has_dask, reason='This is for dask.')
@pytest.mark.parametrize('axis', [0, -1])
@pytest.mark.parametrize('window', [3, 8, 11])
@pytest.mark.parametrize('center', [True, False])
def test_dask_rolling(axis, window, center):
    import dask.array as da

    x = np.array(np.random.randn(100, 40), dtype=float)
    dx = da.from_array(x, chunks=[(6, 30, 30, 20, 14), 8])

    expected = rolling_window(
        x, axis=axis, window=window, center=center, fill_value=np.nan
    )
    actual = rolling_window(
        dx, axis=axis, window=window, center=center, fill_value=np.nan
    )
    assert isinstance(actual, da.Array)
    assert_array_equal(actual, expected)
    assert actual.shape == expected.shape

    # we need to take care of window size if chunk size is small
    # window/2 should be smaller than the smallest chunk size.
    with pytest.raises(ValueError):
        rolling_window(dx, axis=axis, window=100, center=center, fill_value=np.nan)


@pytest.mark.skipif(not has_dask, reason='This is for dask.')
@pytest.mark.parametrize('axis', [0, -1, 1])
@pytest.mark.parametrize('edge_order', [1, 2])
def test_dask_gradient(axis, edge_order):
    import dask.array as da

    array = np.array(np.random.randn(100, 5, 40))
    x = np.exp(np.linspace(0, 1, array.shape[axis]))

    darray = da.from_array(array, chunks=[(6, 30, 30, 20, 14), 5, 8])
    expected = gradient(array, x, axis=axis, edge_order=edge_order)
    actual = gradient(darray, x, axis=axis, edge_order=edge_order)

    assert isinstance(actual, da.Array)
    assert_array_equal(actual, expected)


@pytest.mark.parametrize('dim_num', [1, 2])
@pytest.mark.parametrize('dtype', [float, int, np.float32, np.bool_])
@pytest.mark.parametrize('dask', [False, True])
@pytest.mark.parametrize('func', ['sum', 'prod'])
@pytest.mark.parametrize('aggdim', [None, 'x'])
def test_min_count(dim_num, dtype, dask, func, aggdim):
    if dask and not has_dask:
        pytest.skip('requires dask')

    da = construct_dataarray(dim_num, dtype, contains_nan=True, dask=dask)
    min_count = 3

    actual = getattr(da, func)(dim=aggdim, skipna=True, min_count=min_count)
    expected = series_reduce(da, func, skipna=True, dim=aggdim, min_count=min_count)
    assert_allclose(actual, expected)
    assert_dask_array(actual, dask)


@pytest.mark.parametrize('func', ['sum', 'prod'])
def test_min_count_dataset(func):
    da = construct_dataarray(2, dtype=float, contains_nan=True, dask=False)
    ds = Dataset({'var1': da}, coords={'scalar': 0})
    actual = getattr(ds, func)(dim='x', skipna=True, min_count=3)['var1']
    expected = getattr(ds['var1'], func)(dim='x', skipna=True, min_count=3)
    assert_allclose(actual, expected)


@pytest.mark.parametrize('dtype', [float, int, np.float32, np.bool_])
@pytest.mark.parametrize('dask', [False, True])
@pytest.mark.parametrize('func', ['sum', 'prod'])
def test_multiple_dims(dtype, dask, func):
    if dask and not has_dask:
        pytest.skip('requires dask')
    da = construct_dataarray(3, dtype, contains_nan=True, dask=dask)

    actual = getattr(da, func)(('x', 'y'))
    expected = getattr(getattr(da, func)('x'), func)('y')
    assert_allclose(actual, expected)


def test_docs():
    # with min_count
    actual = DataArray.sum.__doc__
    expected = dedent(
        """\
        Reduce this DataArray's data by applying `sum` along some dimension(s).

        Parameters
        ----------
        dim : str or sequence of str, optional
            Dimension(s) over which to apply `sum`.
        axis : int or sequence of int, optional
            Axis(es) over which to apply `sum`. Only one of the 'dim'
            and 'axis' arguments can be supplied. If neither are supplied, then
            `sum` is calculated over axes.
        skipna : bool, optional
            If True, skip missing values (as marked by NaN). By default, only
            skips missing values for float dtypes; other dtypes either do not
            have a sentinel missing value (int) or skipna=True has not been
            implemented (object, datetime64 or timedelta64).
        min_count : int, default None
            The required number of valid values to perform the operation.
            If fewer than min_count non-NA values are present the result will
            be NA. New in version 0.10.8: Added with the default being None.
        keep_attrs : bool, optional
            If True, the attributes (`attrs`) will be copied from the original
            object to the new one.  If False (default), the new object will be
            returned without attributes.
        **kwargs : dict
            Additional keyword arguments passed on to the appropriate array
            function for calculating `sum` on this object's data.

        Returns
        -------
        reduced : DataArray
            New DataArray object with `sum` applied to its data and the
            indicated dimension(s) removed.
        """
    )
    assert actual == expected

    # without min_count
    actual = DataArray.std.__doc__
    expected = dedent(
        """\
        Reduce this DataArray's data by applying `std` along some dimension(s).

        Parameters
        ----------
        dim : str or sequence of str, optional
            Dimension(s) over which to apply `std`.
        axis : int or sequence of int, optional
            Axis(es) over which to apply `std`. Only one of the 'dim'
            and 'axis' arguments can be supplied. If neither are supplied, then
            `std` is calculated over axes.
        skipna : bool, optional
            If True, skip missing values (as marked by NaN). By default, only
            skips missing values for float dtypes; other dtypes either do not
            have a sentinel missing value (int) or skipna=True has not been
            implemented (object, datetime64 or timedelta64).
        keep_attrs : bool, optional
            If True, the attributes (`attrs`) will be copied from the original
            object to the new one.  If False (default), the new object will be
            returned without attributes.
        **kwargs : dict
            Additional keyword arguments passed on to the appropriate array
            function for calculating `std` on this object's data.

        Returns
        -------
        reduced : DataArray
            New DataArray object with `std` applied to its data and the
            indicated dimension(s) removed.
        """
    )
    assert actual == expected


def test_datetime_to_numeric_datetime64():
    times = pd.date_range('2000', periods=5, freq='7D').values
    result = duck_array_ops.datetime_to_numeric(times, datetime_unit='h')
    expected = 24 * np.arange(0, 35, 7)
    np.testing.assert_array_equal(result, expected)

    offset = times[1]
    result = duck_array_ops.datetime_to_numeric(times, offset=offset, datetime_unit='h')
    expected = 24 * np.arange(-7, 28, 7)
    np.testing.assert_array_equal(result, expected)

    dtype = np.float32
    result = duck_array_ops.datetime_to_numeric(times, datetime_unit='h', dtype=dtype)
    expected = 24 * np.arange(0, 35, 7).astype(dtype)
    np.testing.assert_array_equal(result, expected)


@requires_cftime
def test_datetime_to_numeric_cftime():
    times = cftime_range('2000', periods=5, freq='7D', calendar='standard').values
    result = duck_array_ops.datetime_to_numeric(times, datetime_unit='h', dtype=int)
    expected = 24 * np.arange(0, 35, 7)
    np.testing.assert_array_equal(result, expected)

    offset = times[1]
    result = duck_array_ops.datetime_to_numeric(
        times, offset=offset, datetime_unit='h', dtype=int
    )
    expected = 24 * np.arange(-7, 28, 7)
    np.testing.assert_array_equal(result, expected)

    dtype = np.float32
    result = duck_array_ops.datetime_to_numeric(times, datetime_unit='h', dtype=dtype)
    expected = 24 * np.arange(0, 35, 7).astype(dtype)
    np.testing.assert_array_equal(result, expected)


@requires_cftime
def test_datetime_to_numeric_potential_overflow():
    import cftime

    times = pd.date_range('2000', periods=5, freq='7D').values.astype('datetime64[us]')
    cftimes = cftime_range(
        '2000', periods=5, freq='7D', calendar='proleptic_gregorian'
    ).values

    offset = np.datetime64('0001-01-01')
    cfoffset = cftime.DatetimeProlepticGregorian(1, 1, 1)

    result = duck_array_ops.datetime_to_numeric(
        times, offset=offset, datetime_unit='D', dtype=int
    )
    cfresult = duck_array_ops.datetime_to_numeric(
        cftimes, offset=cfoffset, datetime_unit='D', dtype=int
    )

    expected = 730119 + np.arange(0, 35, 7)

    np.testing.assert_array_equal(result, expected)
    np.testing.assert_array_equal(cfresult, expected)


def test_py_timedelta_to_float():
    assert py_timedelta_to_float(dt.timedelta(days=1), 'ns') == 86400 * 1e9
    assert py_timedelta_to_float(dt.timedelta(days=1e6), 'ps') == 86400 * 1e18
    assert py_timedelta_to_float(dt.timedelta(days=1e6), 'ns') == 86400 * 1e15
    assert py_timedelta_to_float(dt.timedelta(days=1e6), 'us') == 86400 * 1e12
    assert py_timedelta_to_float(dt.timedelta(days=1e6), 'ms') == 86400 * 1e9
    assert py_timedelta_to_float(dt.timedelta(days=1e6), 's') == 86400 * 1e6
    assert py_timedelta_to_float(dt.timedelta(days=1e6), 'D') == 1e6


@pytest.mark.parametrize(
    'td, expected',
    ([np.timedelta64(1, 'D'), 86400 * 1e9], [np.timedelta64(1, 'ns'), 1.0]),
)
def test_np_timedelta64_to_float(td, expected):
    out = np_timedelta64_to_float(td, datetime_unit='ns')
    np.testing.assert_allclose(out, expected)
    assert isinstance(out, float)

    out = np_timedelta64_to_float(np.atleast_1d(td), datetime_unit='ns')
    np.testing.assert_allclose(out, expected)


@pytest.mark.parametrize(
    'td, expected', ([pd.Timedelta(1, 'D'), 86400 * 1e9], [pd.Timedelta(1, 'ns'), 1.0])
)
def test_pd_timedelta_to_float(td, expected):
    out = pd_timedelta_to_float(td, datetime_unit='ns')
    np.testing.assert_allclose(out, expected)
    assert isinstance(out, float)


@pytest.mark.parametrize(
    'td', [dt.timedelta(days=1), np.timedelta64(1, 'D'), pd.Timedelta(1, 'D'), '1 day']
)
def test_timedelta_to_numeric(td):
    # Scalar input
    out = timedelta_to_numeric(td, 'ns')
    np.testing.assert_allclose(out, 86400 * 1e9)
    assert isinstance(out, float)


@pytest.mark.parametrize('use_dask', [True, False])
@pytest.mark.parametrize('skipna', [True, False])
def test_least_squares(use_dask, skipna):
    if use_dask and not has_dask:
        pytest.skip('requires dask')
    lhs = np.array([[1, 2], [1, 2], [3, 2]])
    rhs = DataArray(np.array([3, 5, 7]), dims=('y',))

    if use_dask:
        rhs = rhs.chunk({'y': 1})

    coeffs, residuals = least_squares(lhs, rhs.data, skipna=skipna)

    np.testing.assert_allclose(coeffs, [1.5, 1.25])
    np.testing.assert_allclose(residuals, [2.0])
