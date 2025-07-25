"""Tests for input validation functions"""

import os
import warnings
from itertools import product
from tempfile import NamedTemporaryFile

import numpy as np
import pytest
import scipy.sparse as sp
import sklearn
from scipy import __version__ as scipy_version
from sklearn.datasets import make_blobs
from sklearn.ensemble import RandomForestRegressor
from sklearn.exceptions import DataConversionWarning, NotFittedError
from sklearn.linear_model import ARDRegression
from sklearn.neighbors import KNeighborsClassifier
from sklearn.random_projection import sparse_random_matrix
from sklearn.svm import SVR
from sklearn.utils import (
    as_float_array,
    check_array,
    check_symmetric,
    check_X_y,
    deprecated,
)
from sklearn.utils.estimator_checks import NotAnArray
from sklearn.utils.mocking import MockDataFrame
from sklearn.utils.testing import (
    SkipTest,
    TempMemmap,
    assert_allclose_dense_sparse,
    assert_array_equal,
    assert_equal,
    assert_false,
    assert_no_warnings,
    assert_raise_message,
    assert_raises,
    assert_raises_regex,
    assert_true,
    assert_warns,
    assert_warns_message,
    ignore_warnings,
)
from sklearn.utils.validation import (
    LARGE_SPARSE_SUPPORTED,
    assert_all_finite,
    check_consistent_length,
    check_is_fitted,
    check_memory,
    has_fit_parameter,
)


def test_as_float_array():
    # Test function for as_float_array
    X = np.ones((3, 10), dtype=np.int32)
    X = X + np.arange(10, dtype=np.int32)
    X2 = as_float_array(X, copy=False)
    assert_equal(X2.dtype, np.float32)
    # Another test
    X = X.astype(np.int64)
    X2 = as_float_array(X, copy=True)
    # Checking that the array wasn't overwritten
    assert_true(as_float_array(X, False) is not X)
    assert_equal(X2.dtype, np.float64)
    # Test int dtypes <= 32bit
    tested_dtypes = [
        np.bool,
        np.int8,
        np.int16,
        np.int32,
        np.uint8,
        np.uint16,
        np.uint32,
    ]
    for dtype in tested_dtypes:
        X = X.astype(dtype)
        X2 = as_float_array(X)
        assert_equal(X2.dtype, np.float32)

    # Test object dtype
    X = X.astype(object)
    X2 = as_float_array(X, copy=True)
    assert_equal(X2.dtype, np.float64)

    # Here, X is of the right type, it shouldn't be modified
    X = np.ones((3, 2), dtype=np.float32)
    assert_true(as_float_array(X, copy=False) is X)
    # Test that if X is fortran ordered it stays
    X = np.asfortranarray(X)
    assert_true(np.isfortran(as_float_array(X, copy=True)))

    # Test the copy parameter with some matrices
    matrices = [
        np.matrix(np.arange(5)),
        sp.csc_matrix(np.arange(5)).toarray(),
        sparse_random_matrix(10, 10, density=0.10).toarray(),
    ]
    for M in matrices:
        N = as_float_array(M, copy=True)
        N[0, 0] = np.nan
        assert_false(np.isnan(M).any())


@pytest.mark.parametrize('X', [(np.random.random((10, 2))), (sp.rand(10, 2).tocsr())])
def test_as_float_array_nan(X):
    X[5, 0] = np.nan
    X[6, 1] = np.nan
    X_converted = as_float_array(X, force_all_finite='allow-nan')
    assert_allclose_dense_sparse(X_converted, X)


def test_np_matrix():
    # Confirm that input validation code does not return np.matrix
    X = np.arange(12).reshape(3, 4)

    assert_false(isinstance(as_float_array(X), np.matrix))
    assert_false(isinstance(as_float_array(np.matrix(X)), np.matrix))
    assert_false(isinstance(as_float_array(sp.csc_matrix(X)), np.matrix))


def test_memmap():
    # Confirm that input validation code doesn't copy memory mapped arrays

    asflt = lambda x: as_float_array(x, copy=False)

    with NamedTemporaryFile(prefix='sklearn-test') as tmp:
        M = np.memmap(tmp, shape=(10, 10), dtype=np.float32)
        M[:] = 0

        for f in (check_array, np.asarray, asflt):
            X = f(M)
            X[:] = 1
            assert_array_equal(X.ravel(), M.ravel())
            X[:] = 0


def test_ordering():
    # Check that ordering is enforced correctly by validation utilities.
    # We need to check each validation utility, because a 'copy' without
    # 'order=K' will kill the ordering.
    X = np.ones((10, 5))
    for A in X, X.T:
        for copy in (True, False):
            B = check_array(A, order='C', copy=copy)
            assert_true(B.flags['C_CONTIGUOUS'])
            B = check_array(A, order='F', copy=copy)
            assert_true(B.flags['F_CONTIGUOUS'])
            if copy:
                assert_false(A is B)

    X = sp.csr_matrix(X)
    X.data = X.data[::-1]
    assert_false(X.data.flags['C_CONTIGUOUS'])


@pytest.mark.parametrize(
    'value, force_all_finite', [(np.inf, False), (np.nan, 'allow-nan'), (np.nan, False)]
)
@pytest.mark.parametrize('retype', [np.asarray, sp.csr_matrix])
def test_check_array_force_all_finite_valid(value, force_all_finite, retype):
    X = retype(np.arange(4).reshape(2, 2).astype(np.float))
    X[0, 0] = value
    X_checked = check_array(X, force_all_finite=force_all_finite, accept_sparse=True)
    assert_allclose_dense_sparse(X, X_checked)


@pytest.mark.parametrize(
    'value, force_all_finite, match_msg',
    [
        (np.inf, True, 'Input contains NaN, infinity'),
        (np.inf, 'allow-nan', 'Input contains infinity'),
        (np.nan, True, 'Input contains NaN, infinity'),
        (np.nan, 'allow-inf', 'force_all_finite should be a bool or "allow-nan"'),
        (np.nan, 1, 'force_all_finite should be a bool or "allow-nan"'),
    ],
)
@pytest.mark.parametrize('retype', [np.asarray, sp.csr_matrix])
def test_check_array_force_all_finiteinvalid(
    value, force_all_finite, match_msg, retype
):
    X = retype(np.arange(4).reshape(2, 2).astype(np.float))
    X[0, 0] = value
    with pytest.raises(ValueError, message=match_msg):
        check_array(X, force_all_finite=force_all_finite, accept_sparse=True)


@ignore_warnings
def test_check_array():
    # accept_sparse == None
    # raise error on sparse inputs
    X = [[1, 2], [3, 4]]
    X_csr = sp.csr_matrix(X)
    assert_raises(TypeError, check_array, X_csr)
    # ensure_2d=False
    X_array = check_array([0, 1, 2], ensure_2d=False)
    assert_equal(X_array.ndim, 1)
    # ensure_2d=True with 1d array
    assert_raise_message(
        ValueError,
        'Expected 2D array, got 1D array instead',
        check_array,
        [0, 1, 2],
        ensure_2d=True,
    )
    # ensure_2d=True with scalar array
    assert_raise_message(
        ValueError,
        'Expected 2D array, got scalar array instead',
        check_array,
        10,
        ensure_2d=True,
    )
    # don't allow ndim > 3
    X_ndim = np.arange(8).reshape(2, 2, 2)
    assert_raises(ValueError, check_array, X_ndim)
    check_array(X_ndim, allow_nd=True)  # doesn't raise

    # dtype and order enforcement.
    X_C = np.arange(4).reshape(2, 2).copy('C')
    X_F = X_C.copy('F')
    X_int = X_C.astype(np.int)
    X_float = X_C.astype(np.float)
    Xs = [X_C, X_F, X_int, X_float]
    dtypes = [np.int32, np.int, np.float, np.float32, None, np.bool, object]
    orders = ['C', 'F', None]
    copys = [True, False]

    for X, dtype, order, copy in product(Xs, dtypes, orders, copys):
        X_checked = check_array(X, dtype=dtype, order=order, copy=copy)
        if dtype is not None:
            assert_equal(X_checked.dtype, dtype)
        else:
            assert_equal(X_checked.dtype, X.dtype)
        if order == 'C':
            assert_true(X_checked.flags['C_CONTIGUOUS'])
            assert_false(X_checked.flags['F_CONTIGUOUS'])
        elif order == 'F':
            assert_true(X_checked.flags['F_CONTIGUOUS'])
            assert_false(X_checked.flags['C_CONTIGUOUS'])
        if copy:
            assert_false(X is X_checked)
        else:
            # doesn't copy if it was already good
            if (
                X.dtype == X_checked.dtype
                and X_checked.flags['C_CONTIGUOUS'] == X.flags['C_CONTIGUOUS']
                and X_checked.flags['F_CONTIGUOUS'] == X.flags['F_CONTIGUOUS']
            ):
                assert_true(X is X_checked)

    # allowed sparse != None
    X_csc = sp.csc_matrix(X_C)
    X_coo = X_csc.tocoo()
    X_dok = X_csc.todok()
    X_int = X_csc.astype(np.int)
    X_float = X_csc.astype(np.float)

    Xs = [X_csc, X_coo, X_dok, X_int, X_float]
    accept_sparses = [['csr', 'coo'], ['coo', 'dok']]
    for X, dtype, accept_sparse, copy in product(Xs, dtypes, accept_sparses, copys):
        with warnings.catch_warnings(record=True) as w:
            X_checked = check_array(
                X, dtype=dtype, accept_sparse=accept_sparse, copy=copy
            )
        if (dtype is object or sp.isspmatrix_dok(X)) and len(w):
            message = str(w[0].message)
            messages = [
                'object dtype is not supported by sparse matrices',
                "Can't check dok sparse matrix for nan or inf.",
            ]
            assert_true(message in messages)
        else:
            assert_equal(len(w), 0)
        if dtype is not None:
            assert_equal(X_checked.dtype, dtype)
        else:
            assert_equal(X_checked.dtype, X.dtype)
        if X.format in accept_sparse:
            # no change if allowed
            assert_equal(X.format, X_checked.format)
        else:
            # got converted
            assert_equal(X_checked.format, accept_sparse[0])
        if copy:
            assert_false(X is X_checked)
        else:
            # doesn't copy if it was already good
            if X.dtype == X_checked.dtype and X.format == X_checked.format:
                assert_true(X is X_checked)

    # other input formats
    # convert lists to arrays
    X_dense = check_array([[1, 2], [3, 4]])
    assert_true(isinstance(X_dense, np.ndarray))
    # raise on too deep lists
    assert_raises(ValueError, check_array, X_ndim.tolist())
    check_array(X_ndim.tolist(), allow_nd=True)  # doesn't raise
    # convert weird stuff to arrays
    X_no_array = NotAnArray(X_dense)
    result = check_array(X_no_array)
    assert_true(isinstance(result, np.ndarray))

    # deprecation warning if string-like array with dtype="numeric"
    X_str = [['a', 'b'], ['c', 'd']]
    assert_warns_message(
        FutureWarning,
        'arrays of strings will be interpreted as decimal numbers if '
        "parameter 'dtype' is 'numeric'. It is recommended that you convert "
        'the array to type np.float64 before passing it to check_array.',
        check_array,
        X_str,
        'numeric',
    )
    assert_warns_message(
        FutureWarning,
        'arrays of strings will be interpreted as decimal numbers if '
        "parameter 'dtype' is 'numeric'. It is recommended that you convert "
        'the array to type np.float64 before passing it to check_array.',
        check_array,
        np.array(X_str, dtype='U'),
        'numeric',
    )
    assert_warns_message(
        FutureWarning,
        'arrays of strings will be interpreted as decimal numbers if '
        "parameter 'dtype' is 'numeric'. It is recommended that you convert "
        'the array to type np.float64 before passing it to check_array.',
        check_array,
        np.array(X_str, dtype='S'),
        'numeric',
    )

    # deprecation warning if byte-like array with dtype="numeric"
    X_bytes = [[b'a', b'b'], [b'c', b'd']]
    assert_warns_message(
        FutureWarning,
        'arrays of strings will be interpreted as decimal numbers if '
        "parameter 'dtype' is 'numeric'. It is recommended that you convert "
        'the array to type np.float64 before passing it to check_array.',
        check_array,
        X_bytes,
        'numeric',
    )
    assert_warns_message(
        FutureWarning,
        'arrays of strings will be interpreted as decimal numbers if '
        "parameter 'dtype' is 'numeric'. It is recommended that you convert "
        'the array to type np.float64 before passing it to check_array.',
        check_array,
        np.array(X_bytes, dtype='V1'),
        'numeric',
    )


def test_check_array_pandas_dtype_object_conversion():
    # test that data-frame like objects with dtype object
    # get converted
    X = np.array([[1, 2, 3], [4, 5, 6], [7, 8, 9]], dtype=np.object)
    X_df = MockDataFrame(X)
    assert_equal(check_array(X_df).dtype.kind, 'f')
    assert_equal(check_array(X_df, ensure_2d=False).dtype.kind, 'f')
    # smoke-test against dataframes with column named "dtype"
    X_df.dtype = 'Hans'
    assert_equal(check_array(X_df, ensure_2d=False).dtype.kind, 'f')


def test_check_array_on_mock_dataframe():
    arr = np.array([[0.2, 0.7], [0.6, 0.5], [0.4, 0.1], [0.7, 0.2]])
    mock_df = MockDataFrame(arr)
    checked_arr = check_array(mock_df)
    assert_equal(checked_arr.dtype, arr.dtype)
    checked_arr = check_array(mock_df, dtype=np.float32)
    assert_equal(checked_arr.dtype, np.dtype(np.float32))


def test_check_array_dtype_stability():
    # test that lists with ints don't get converted to floats
    X = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
    assert_equal(check_array(X).dtype.kind, 'i')
    assert_equal(check_array(X, ensure_2d=False).dtype.kind, 'i')


def test_check_array_dtype_warning():
    X_int_list = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
    X_float64 = np.asarray(X_int_list, dtype=np.float64)
    X_float32 = np.asarray(X_int_list, dtype=np.float32)
    X_int64 = np.asarray(X_int_list, dtype=np.int64)
    X_csr_float64 = sp.csr_matrix(X_float64)
    X_csr_float32 = sp.csr_matrix(X_float32)
    X_csc_float32 = sp.csc_matrix(X_float32)
    X_csc_int32 = sp.csc_matrix(X_int64, dtype=np.int32)
    y = [0, 0, 1]
    integer_data = [X_int64, X_csc_int32]
    float64_data = [X_float64, X_csr_float64]
    float32_data = [X_float32, X_csr_float32, X_csc_float32]
    for X in integer_data:
        X_checked = assert_no_warnings(
            check_array, X, dtype=np.float64, accept_sparse=True
        )
        assert_equal(X_checked.dtype, np.float64)

        X_checked = assert_warns(
            DataConversionWarning,
            check_array,
            X,
            dtype=np.float64,
            accept_sparse=True,
            warn_on_dtype=True,
        )
        assert_equal(X_checked.dtype, np.float64)

        # Check that the warning message includes the name of the Estimator
        X_checked = assert_warns_message(
            DataConversionWarning,
            'SomeEstimator',
            check_array,
            X,
            dtype=[np.float64, np.float32],
            accept_sparse=True,
            warn_on_dtype=True,
            estimator='SomeEstimator',
        )
        assert_equal(X_checked.dtype, np.float64)

        X_checked, y_checked = assert_warns_message(
            DataConversionWarning,
            'KNeighborsClassifier',
            check_X_y,
            X,
            y,
            dtype=np.float64,
            accept_sparse=True,
            warn_on_dtype=True,
            estimator=KNeighborsClassifier(),
        )

        assert_equal(X_checked.dtype, np.float64)

    for X in float64_data:
        X_checked = assert_no_warnings(
            check_array, X, dtype=np.float64, accept_sparse=True, warn_on_dtype=True
        )
        assert_equal(X_checked.dtype, np.float64)
        X_checked = assert_no_warnings(
            check_array, X, dtype=np.float64, accept_sparse=True, warn_on_dtype=False
        )
        assert_equal(X_checked.dtype, np.float64)

    for X in float32_data:
        X_checked = assert_no_warnings(
            check_array, X, dtype=[np.float64, np.float32], accept_sparse=True
        )
        assert_equal(X_checked.dtype, np.float32)
        assert_true(X_checked is X)

        X_checked = assert_no_warnings(
            check_array,
            X,
            dtype=[np.float64, np.float32],
            accept_sparse=['csr', 'dok'],
            copy=True,
        )
        assert_equal(X_checked.dtype, np.float32)
        assert_false(X_checked is X)

    X_checked = assert_no_warnings(
        check_array,
        X_csc_float32,
        dtype=[np.float64, np.float32],
        accept_sparse=['csr', 'dok'],
        copy=False,
    )
    assert_equal(X_checked.dtype, np.float32)
    assert_false(X_checked is X_csc_float32)
    assert_equal(X_checked.format, 'csr')


def test_check_array_accept_sparse_type_exception():
    X = [[1, 2], [3, 4]]
    X_csr = sp.csr_matrix(X)
    invalid_type = SVR()

    msg = (
        'A sparse matrix was passed, but dense data is required. '
        'Use X.toarray() to convert to a dense numpy array.'
    )
    assert_raise_message(TypeError, msg, check_array, X_csr, accept_sparse=False)
    assert_raise_message(TypeError, msg, check_array, X_csr, accept_sparse=None)

    msg = (
        "Parameter 'accept_sparse' should be a string, "
        "boolean or list of strings. You provided 'accept_sparse={}'."
    )
    assert_raise_message(
        ValueError,
        msg.format(invalid_type),
        check_array,
        X_csr,
        accept_sparse=invalid_type,
    )

    msg = (
        "When providing 'accept_sparse' as a tuple or list, "
        'it must contain at least one string value.'
    )
    assert_raise_message(
        ValueError, msg.format([]), check_array, X_csr, accept_sparse=[]
    )
    assert_raise_message(
        ValueError, msg.format(()), check_array, X_csr, accept_sparse=()
    )

    assert_raise_message(
        TypeError, 'SVR', check_array, X_csr, accept_sparse=[invalid_type]
    )

    # Test deprecation of 'None'
    assert_warns(DeprecationWarning, check_array, X, accept_sparse=None)


def test_check_array_accept_sparse_no_exception():
    X = [[1, 2], [3, 4]]
    X_csr = sp.csr_matrix(X)

    check_array(X_csr, accept_sparse=True)
    check_array(X_csr, accept_sparse='csr')
    check_array(X_csr, accept_sparse=['csr'])
    check_array(X_csr, accept_sparse=('csr',))


@pytest.fixture(params=['csr', 'csc', 'coo', 'bsr'])
def X_64bit(request):
    X = sp.rand(20, 10, format=request.param)
    for attr in ['indices', 'indptr', 'row', 'col']:
        if hasattr(X, attr):
            setattr(X, attr, getattr(X, attr).astype('int64'))
    yield X


def test_check_array_accept_large_sparse_no_exception(X_64bit):
    # When large sparse are allowed
    if LARGE_SPARSE_SUPPORTED:
        check_array(X_64bit, accept_large_sparse=True, accept_sparse=True)


def test_check_array_accept_large_sparse_raise_exception(X_64bit):
    # When large sparse are not allowed
    if LARGE_SPARSE_SUPPORTED:
        msg = (
            'Only sparse matrices with 32-bit integer indices '
            'are accepted. Got int64 indices.'
        )
        assert_raise_message(
            ValueError,
            msg,
            check_array,
            X_64bit,
            accept_sparse=True,
            accept_large_sparse=False,
        )


def test_check_array_large_indices_non_supported_scipy_version(X_64bit):
    # Large indices should not be allowed for scipy<0.14.0
    if not LARGE_SPARSE_SUPPORTED:
        msg = (
            'Scipy version %s does not support large'
            ' indices, please upgrade your scipy'
            ' to 0.14.0 or above' % scipy_version
        )
        assert_raise_message(ValueError, msg, check_array, X_64bit, accept_sparse='csc')


def test_check_array_min_samples_and_features_messages():
    # empty list is considered 2D by default:
    msg = '0 feature(s) (shape=(1, 0)) while a minimum of 1 is required.'
    assert_raise_message(ValueError, msg, check_array, [[]])

    # If considered a 1D collection when ensure_2d=False, then the minimum
    # number of samples will break:
    msg = '0 sample(s) (shape=(0,)) while a minimum of 1 is required.'
    assert_raise_message(ValueError, msg, check_array, [], ensure_2d=False)

    # Invalid edge case when checking the default minimum sample of a scalar
    msg = 'Singleton array array(42) cannot be considered a valid collection.'
    assert_raise_message(TypeError, msg, check_array, 42, ensure_2d=False)

    # Simulate a model that would need at least 2 samples to be well defined
    X = np.ones((1, 10))
    y = np.ones(1)
    msg = '1 sample(s) (shape=(1, 10)) while a minimum of 2 is required.'
    assert_raise_message(ValueError, msg, check_X_y, X, y, ensure_min_samples=2)

    # The same message is raised if the data has 2 dimensions even if this is
    # not mandatory
    assert_raise_message(
        ValueError, msg, check_X_y, X, y, ensure_min_samples=2, ensure_2d=False
    )

    # Simulate a model that would require at least 3 features (e.g. SelectKBest
    # with k=3)
    X = np.ones((10, 2))
    y = np.ones(2)
    msg = '2 feature(s) (shape=(10, 2)) while a minimum of 3 is required.'
    assert_raise_message(ValueError, msg, check_X_y, X, y, ensure_min_features=3)

    # Only the feature check is enabled whenever the number of dimensions is 2
    # even if allow_nd is enabled:
    assert_raise_message(
        ValueError, msg, check_X_y, X, y, ensure_min_features=3, allow_nd=True
    )

    # Simulate a case where a pipeline stage as trimmed all the features of a
    # 2D dataset.
    X = np.empty(0).reshape(10, 0)
    y = np.ones(10)
    msg = '0 feature(s) (shape=(10, 0)) while a minimum of 1 is required.'
    assert_raise_message(ValueError, msg, check_X_y, X, y)

    # nd-data is not checked for any minimum number of features by default:
    X = np.ones((10, 0, 28, 28))
    y = np.ones(10)
    X_checked, y_checked = check_X_y(X, y, allow_nd=True)
    assert_array_equal(X, X_checked)
    assert_array_equal(y, y_checked)


def test_check_array_complex_data_error():
    X = np.array([[1 + 2j, 3 + 4j, 5 + 7j], [2 + 3j, 4 + 5j, 6 + 7j]])
    assert_raises_regex(ValueError, 'Complex data not supported', check_array, X)

    # list of lists
    X = [[1 + 2j, 3 + 4j, 5 + 7j], [2 + 3j, 4 + 5j, 6 + 7j]]
    assert_raises_regex(ValueError, 'Complex data not supported', check_array, X)

    # tuple of tuples
    X = ((1 + 2j, 3 + 4j, 5 + 7j), (2 + 3j, 4 + 5j, 6 + 7j))
    assert_raises_regex(ValueError, 'Complex data not supported', check_array, X)

    # list of np arrays
    X = [np.array([1 + 2j, 3 + 4j, 5 + 7j]), np.array([2 + 3j, 4 + 5j, 6 + 7j])]
    assert_raises_regex(ValueError, 'Complex data not supported', check_array, X)

    # tuple of np arrays
    X = (np.array([1 + 2j, 3 + 4j, 5 + 7j]), np.array([2 + 3j, 4 + 5j, 6 + 7j]))
    assert_raises_regex(ValueError, 'Complex data not supported', check_array, X)

    # dataframe
    X = MockDataFrame(np.array([[1 + 2j, 3 + 4j, 5 + 7j], [2 + 3j, 4 + 5j, 6 + 7j]]))
    assert_raises_regex(ValueError, 'Complex data not supported', check_array, X)

    # sparse matrix
    X = sp.coo_matrix([[0, 1 + 2j], [0, 0]])
    assert_raises_regex(ValueError, 'Complex data not supported', check_array, X)


def test_has_fit_parameter():
    assert_false(has_fit_parameter(KNeighborsClassifier, 'sample_weight'))
    assert_true(has_fit_parameter(RandomForestRegressor, 'sample_weight'))
    assert_true(has_fit_parameter(SVR, 'sample_weight'))
    assert_true(has_fit_parameter(SVR(), 'sample_weight'))

    class TestClassWithDeprecatedFitMethod:
        @deprecated('Deprecated for the purpose of testing has_fit_parameter')
        def fit(self, X, y, sample_weight=None):
            pass

    assert has_fit_parameter(
        TestClassWithDeprecatedFitMethod, 'sample_weight'
    ), 'has_fit_parameter fails for class with deprecated fit method.'


def test_check_symmetric():
    arr_sym = np.array([[0, 1], [1, 2]])
    arr_bad = np.ones(2)
    arr_asym = np.array([[0, 2], [0, 2]])

    test_arrays = {
        'dense': arr_asym,
        'dok': sp.dok_matrix(arr_asym),
        'csr': sp.csr_matrix(arr_asym),
        'csc': sp.csc_matrix(arr_asym),
        'coo': sp.coo_matrix(arr_asym),
        'lil': sp.lil_matrix(arr_asym),
        'bsr': sp.bsr_matrix(arr_asym),
    }

    # check error for bad inputs
    assert_raises(ValueError, check_symmetric, arr_bad)

    # check that asymmetric arrays are properly symmetrized
    for arr_format, arr in test_arrays.items():
        # Check for warnings and errors
        assert_warns(UserWarning, check_symmetric, arr)
        assert_raises(ValueError, check_symmetric, arr, raise_exception=True)

        output = check_symmetric(arr, raise_warning=False)
        if sp.issparse(output):
            assert_equal(output.format, arr_format)
            assert_array_equal(output.toarray(), arr_sym)
        else:
            assert_array_equal(output, arr_sym)


def test_check_is_fitted():
    # Check is ValueError raised when non estimator instance passed
    assert_raises(ValueError, check_is_fitted, ARDRegression, 'coef_')
    assert_raises(TypeError, check_is_fitted, 'SVR', 'support_')

    ard = ARDRegression()
    svr = SVR(gamma='scale')

    try:
        assert_raises(NotFittedError, check_is_fitted, ard, 'coef_')
        assert_raises(NotFittedError, check_is_fitted, svr, 'support_')
    except ValueError:
        assert False, 'check_is_fitted failed with ValueError'

    # NotFittedError is a subclass of both ValueError and AttributeError
    try:
        check_is_fitted(ard, 'coef_', 'Random message %(name)s, %(name)s')
    except ValueError as e:
        assert_equal(str(e), 'Random message ARDRegression, ARDRegression')

    try:
        check_is_fitted(svr, 'support_', 'Another message %(name)s, %(name)s')
    except AttributeError as e:
        assert_equal(str(e), 'Another message SVR, SVR')

    ard.fit(*make_blobs())
    svr.fit(*make_blobs())

    assert_equal(None, check_is_fitted(ard, 'coef_'))
    assert_equal(None, check_is_fitted(svr, 'support_'))


def test_check_consistent_length():
    check_consistent_length([1], [2], [3], [4], [5])
    check_consistent_length([[1, 2], [[1, 2]]], [1, 2], ['a', 'b'])
    check_consistent_length([1], (2,), np.array([3]), sp.csr_matrix((1, 2)))
    assert_raises_regex(
        ValueError,
        'inconsistent numbers of samples',
        check_consistent_length,
        [1, 2],
        [1],
    )
    assert_raises_regex(
        TypeError, r"got <\w+ 'int'>", check_consistent_length, [1, 2], 1
    )
    assert_raises_regex(
        TypeError, r"got <\w+ 'object'>", check_consistent_length, [1, 2], object()
    )

    assert_raises(TypeError, check_consistent_length, [1, 2], np.array(1))
    # Despite ensembles having __len__ they must raise TypeError
    assert_raises_regex(
        TypeError, 'estimator', check_consistent_length, [1, 2], RandomForestRegressor()
    )
    # XXX: We should have a test with a string, but what is correct behaviour?


def test_check_dataframe_fit_attribute():
    # check pandas dataframe with 'fit' column does not raise error
    # https://github.com/scikit-learn/scikit-learn/issues/8415
    try:
        import pandas as pd

        X = np.array([[1, 2, 3], [4, 5, 6], [7, 8, 9]])
        X_df = pd.DataFrame(X, columns=['a', 'b', 'fit'])
        check_consistent_length(X_df)
    except ImportError:
        raise SkipTest('Pandas not found')


def test_suppress_validation():
    X = np.array([0, np.inf])
    assert_raises(ValueError, assert_all_finite, X)
    sklearn.set_config(assume_finite=True)
    assert_all_finite(X)
    sklearn.set_config(assume_finite=False)
    assert_raises(ValueError, assert_all_finite, X)


class DummyMemory(object):
    def cache(self, func):
        return func


class WrongDummyMemory(object):
    pass


def test_check_memory():
    memory = check_memory('cache_directory')
    assert_equal(memory.cachedir, os.path.join('cache_directory', 'joblib'))
    memory = check_memory(None)
    assert_equal(memory.cachedir, None)
    dummy = DummyMemory()
    memory = check_memory(dummy)
    assert memory is dummy
    assert_raises_regex(
        ValueError,
        "'memory' should be None, a string or"
        ' have the same interface as '
        'sklearn.externals.joblib.Memory.'
        " Got memory='1' instead.",
        check_memory,
        1,
    )
    dummy = WrongDummyMemory()
    assert_raises_regex(
        ValueError,
        "'memory' should be None, a string or"
        ' have the same interface as '
        "sklearn.externals.joblib.Memory. Got memory='{}' "
        'instead.'.format(dummy),
        check_memory,
        dummy,
    )


@pytest.mark.parametrize('copy', [True, False])
def test_check_array_memmap(copy):
    X = np.ones((4, 4))
    with TempMemmap(X, mmap_mode='r') as X_memmap:
        X_checked = check_array(X_memmap, copy=copy)
        assert np.may_share_memory(X_memmap, X_checked) == (not copy)
        assert X_checked.flags['WRITEABLE'] == copy
