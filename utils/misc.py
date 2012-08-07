import collections
from PIL import Image
import itertools
import numpy as np
nax = np.newaxis
import progressbar
import scipy.linalg, scipy.integrate
import sys
import termcolor


def arr2img(arr, rescale=True):
    if rescale:
        assert np.all(0. <= arr) and np.all(arr <= 1.)
        return Image.fromarray((arr*255).astype('uint8'))
    else:
        return Image.fromarray(arr.astype('uint8'))


def is_diag(A):
    return A.shape[0] == A.shape[1] and np.all(A == np.diag(np.diag(A)))

def my_svd(A):
    m, n = A.shape
    if is_diag(A):
        return np.eye(m), np.diag(A), np.eye(m)
    else:
        return scipy.linalg.svd(A, full_matrices=False)

def map_gaussian_matrix(A, B, C, d_1, d_2, d_3, d_4):
    """sample X, where P(X) \propto e^{-J(X)} and
    J(X) = 1/2 \|D_1(AXB - C)D_2\|^2 + 1/2 \|D_3 X D_4\|^2."""
    A_tilde = d_1[:, nax] * A / d_3[nax, :]
    B_tilde = (1. / d_4[:, nax]) * B * d_2[nax, :]
    C_tilde = d_1[:, nax] * C * d_2[nax, :]

    U_A, lambda_A, Vt_A = my_svd(A_tilde)
    V_A = Vt_A.T
    
    U_B, lambda_B, Vt_B = my_svd(B_tilde)
    V_B = Vt_B.T

    Lambda = lambda_A[:, nax] * lambda_B[nax, :]
    Y = Lambda * np.dot(np.dot(U_A.T, C_tilde), V_B) / (1. + Lambda**2)
    X_tilde = np.dot(np.dot(V_A, Y), U_B.T)
    X = (1. / d_3[:, nax]) * X_tilde * (1. / d_4[nax, :])

    return X

def map_gaussian_matrix_em(A, B, C, d_1, d_2, d_3, d_4, obs, X):
    C_ = np.where(obs, C, np.dot(np.dot(A, X), B))
    return map_gaussian_matrix(A, B, C_, d_1, d_2, d_3, d_4)
    

def sample_gaussian_matrix(A, B, C, d_1, d_2, d_3, d_4):
    """sample X, where P(X) \propto e^{-J(X)} and
    J(X) = 1/2 \|D_1(AXB - C)D_2\|^2 + 1/2 \|D_3 X D_4\|^2."""
    A_tilde = d_1[:, nax] * A / d_3[nax, :]
    B_tilde = (1. / d_4[:, nax]) * B * d_2[nax, :]
    C_tilde = d_1[:, nax] * C * d_2[nax, :]

    U_A, lambda_A, Vt_A = my_svd(A_tilde)
    V_A = Vt_A.T

    U_B, lambda_B, Vt_B = my_svd(B_tilde)
    V_B = Vt_B.T

    Lambda = lambda_A[:, nax] * lambda_B[nax, :]
    Y_mean = Lambda * np.dot(np.dot(U_A.T, C_tilde), V_B) / (1. + Lambda**2)
    Y_var = 1. / (1. + Lambda**2)
    Y = np.random.normal(Y_mean, np.sqrt(Y_var))
    X_tilde = np.dot(np.dot(V_A, Y), U_B.T)
    X = (1. / d_3[:, nax]) * X_tilde * (1. / d_4[nax, :])

    return X

def sample_gaussian_matrix_em(A, B, C, d_1, d_2, d_3, d_4, obs, X):
    C_ = np.where(obs, C, np.dot(np.dot(A, X), B))
    return sample_gaussian_matrix(A, B, C_, d_1, d_2, d_3, d_4)



def sample_gaussian_matrix2(A, B, W_X, W_N):
    nrows, ncols = A.shape[1], B.shape[1]
    X = np.zeros((nrows, ncols))
    for j in range(ncols):
        Lambda = np.dot(np.dot(A.T, np.diag(W_N[:,j])), A) + np.diag(W_X[:,j])
        Sigma = np.linalg.inv(Lambda)
        mu = mult([Sigma, A.T, W_N[:,j] * B[:,j]])
        X[:,j] = np.random.multivariate_normal(mu, Sigma)
    return X

def map_gaussian_matrix2(A, B, W_X, W_N):
    nrows, ncols = A.shape[1], B.shape[1]
    X = np.zeros((nrows, ncols))
    for j in range(ncols):
        Lambda = np.dot(np.dot(A.T, np.diag(W_N[:,j])), A) + np.diag(W_X[:,j])
        Sigma = np.linalg.inv(Lambda)
        mu = mult([Sigma, A.T, W_N[:,j] * B[:,j]])
        X[:,j] = mu
    return X



def mult(matrices):
    """Matrix multiplication"""
    prod = matrices[0]
    for mat in matrices[1:]:
        prod = np.dot(prod, mat)
    return prod



def mean_field(J, Lambda, z_init=None):
    n = J.size
    assert J.shape == (n,) and Lambda.shape == (n, n)
    if z_init is not None:
        z = z_init.copy()
    else:
        z = np.zeros(n)

    # move quadratic potentials for one variable to unary terms
    J = J + 0.5 * Lambda[range(n), range(n)]
    Lambda[range(n), range(n)] = 0.

    for tr in range(100):
        for j in range(n):
            Lambda_term = np.dot(Lambda, z)
            odds = -J - Lambda_term
            odds = odds.clip(-100., 100.)   # to avoid the overflow warnings
            z_new = 1. / (1. + np.exp(-odds))
            z[j] = 0.8*z[j] + 0.2*z_new[j]

    return z

NEWLINE_EVERY = 50
dummy_count = [0]
def print_dot(count=None, max=None):
    print_count = (count is not None)
    if count is None:
        dummy_count[0] += 1
        count = dummy_count[0]
    sys.stdout.write('.')
    sys.stdout.flush()
    if count % NEWLINE_EVERY == 0:
        if print_count:
            if max is not None:
                sys.stdout.write(' [%d/%d]' % (count, max))
            else:
                sys.stdout.write(' [%d]' % count)
        sys.stdout.write('\n')
    elif count == max:
        sys.stdout.write('\n')
    sys.stdout.flush()



def sample_noise(N, obs=None, b0=1.):
    if obs is None:
        obs = np.ones(N.shape, dtype=bool)
        
    nrows, ncols = N.shape
    ssq_rows, ssq_cols = sample_noise_tied(N, obs, b0)
    lambda_rows = 1. / ssq_rows
    lambda_cols = 1. / ssq_cols

    a0 = 1.

    for tr in range(10):
        a = a0 + 0.5 * obs.sum(1)
        b = b0 + 0.5 * np.sum(obs * N**2 * lambda_cols[nax,:], axis=1)
        lambda_rows = np.random.gamma(a, 1. / b)

        if np.isscalar(lambda_rows):  # np.random.gamma converts singleton arrays into scalars
            lambda_rows = np.array([lambda_rows])

        a = a0 + 0.5 * obs.sum(0)
        b = b0 + 0.5 * np.sum(obs * N**2 * lambda_rows[:,nax], axis=0)
        lambda_cols = np.random.gamma(a, 1. / b)

        if np.isscalar(lambda_cols):
            lambda_cols = np.array([lambda_cols])

    return 1. / lambda_rows, 1. / lambda_cols

def sample_noise_tied(N, obs=None, b0=1.):
    if obs is None:
        obs = np.ones(N.shape, dtype=bool)
    nrows, ncols = N.shape
    a0 = 1.
    a = a0 + 0.5 * obs.sum()
    b = b0 + 0.5 * np.sum(obs * N**2)
    prec = np.random.gamma(a, 1. / b)

    return np.ones(nrows) / np.sqrt(prec), np.ones(ncols) / np.sqrt(prec)

def sample_col_noise(N):
    nrows, ncols = N.shape
    A0 = 1.
    B0 = 1.
    B0 = np.mean(N**2)   # UNDO
    a = A0 + 0.5 * nrows
    b = B0 + 0.5 * np.sum(N**2, axis=0)
    return 1. / np.random.gamma(a, 1. / b)
        


def combine_precisions(Sigma_v, Lambda_y):
    """compute (Sigma_v + Lambda_y^{-1})^{-1}, where Lambda_y may be low rank"""
    d, Q = scipy.linalg.eigh(Lambda_y)
    zero_count = np.sum(d < 1e-10)
    if zero_count == Lambda_y.shape[0]:
        return np.zeros(Lambda_y.shape)
    Q = Q[:,zero_count:]

    Sigma_v_proj = np.dot(np.dot(Q.T, Sigma_v), Q)
    Lambda_y_proj = np.dot(np.dot(Q.T, Lambda_y), Q)
    ans_proj = scipy.linalg.inv(Sigma_v_proj + scipy.linalg.inv(Lambda_y_proj))
    return np.dot(np.dot(Q, ans_proj), Q.T)



def kalman_filter(mu_0, Sigma_0, A, mu_v, Sigma_v, B, Lambda_n, y):
    nlat = mu_0.size
    nvis, ntime = y.shape

    assert np.allclose(mu_v, 0.)
    
    mu_forward = np.zeros((nlat, ntime))
    Sigma_forward = np.zeros((nlat, nlat, ntime))
    mu = np.zeros((nlat, ntime))
    Sigma = np.zeros((nlat, nlat, ntime))
    mu_forward[:,0] = mu_0
    Sigma_forward[:,:,0] = Sigma_0
    
    # forward propagation
    for t in range(ntime):
        # execute dynamics
        if t > 0:
            mu_forward[:,t] = np.dot(A, mu[:,t-1]) + mu_v
            Sigma_forward[:,:,t] = np.dot(np.dot(A, Sigma[:,:,t-1]), A.T) + Sigma_v

        # account for observations
        Lambda, J, _ = expectation_to_information(Sigma_forward[:,:,t], mu_forward[:,t])
        Lambda += np.dot(np.dot(B.T, Lambda_n[:,:,t]), B)
        J -= np.dot(B.T, np.dot(Lambda_n[:,:,t], y[:,t]))
        Sigma[:,:,t], mu[:,t], _ = information_to_expectation(Lambda, J)

    J_backward = np.zeros((nlat, ntime))
    Lambda_backward = np.zeros((nlat, nlat, ntime))


    # backward propagation
    for t in range(ntime-1)[::-1]:
        Lambda_obs = np.dot(np.dot(B.T, Lambda_n[:,:,t]), B)
        Lambda_prime = Lambda_backward[:,:,t+1] + Lambda_obs
        J_prime = -np.dot(B.T, np.dot(Lambda_n[:,:,t], y[:,t])) + J_backward[:,t+1]
        mu_prime = -np.linalg.lstsq(Lambda_prime, J_prime)[0]

        Lambda_prime = combine_precisions(Sigma_v, Lambda_prime)

        Lambda_backward[:,:,t] = np.dot(np.dot(A.T, Lambda_prime), A)
        mu_backward = np.linalg.lstsq(A, mu_prime)[0]
        J_backward[:,t] = -np.dot(Lambda_backward[:,:,t], mu_backward)

    # combine both directions
    for t in range(ntime):
        Lambda, J, _ = expectation_to_information(Sigma[:,:,t], mu[:,t])
        J += J_backward[:,t]
        Lambda += Lambda_backward[:,:,t]
        Sigma[:,:,t], mu[:,t], _ = information_to_expectation(Lambda, J)

    return mu, Sigma


    
def logdet(A):
    """Compute the log-determinant of a symmetric positive definite matrix A using the Cholesky factorization."""
    L = np.linalg.cholesky(A)
    return 2 * np.sum(np.log(np.diag(L)))

def slice_list(lst, slc):
    """Slice a Python list as if it were an array."""
    if isinstance(slc, np.ndarray):
        slc = slc.ravel()
    idxs = np.arange(len(lst))[slc]
    return [lst[i] for i in idxs]

def extract_slices(slc):
    if type(slc) == tuple:
        result = []
        for s in slc:
            if isinstance(s, np.ndarray):
                result.append(s.ravel())
            else:
                result.append(s)
        return tuple(result)
    else:
        return slc

def _err_string(arr1, arr2):
    try:
        if np.allclose(arr1, arr2):
            return 'OK'
        elif arr1.shape == arr2.shape:
            return 'off by %s' % np.abs(arr1 - arr2).max()
        else:
            return 'incorrect shapes: %s and %s' % (arr1.shape, arr2.shape)
    except:
        return 'error comparing'

err_info = collections.defaultdict(list)
def set_err_info(key, info):
    err_info[key] = info

def summarize_error(key):
    """Print a helpful description of the reason a condition was not satisfied. Intended usage:
        assert pot1.allclose(pot2), summarize_error()"""
    if type(err_info[key]) == str:
        return '    ' + err_info[key]
    else:
        return '\n' + '\n'.join(['    %s: %s' % (name, err) for name, err in err_info[key]]) + '\n'


def broadcast(idx, shape):
    result = []
    for i, d in zip(idx, shape):
        if d == 1:
            result.append(0)
        else:
            result.append(i)
    return tuple(result)

def full_shape(shapes):
    """The shape of the full array that results from broadcasting the arrays of the given shapes."""
    return tuple(np.array(shapes).max(0))


def array_map(fn, arrs, n):
    """Takes a list of arrays a_1, ..., a_n where the elements of the first n dimensions line up. For every possible
    index into the first n dimensions, apply fn to the corresponding slices, and combine the results into
    an n-dimensional array. Supports broadcasting but does not prepend 1's to the shapes."""
    # we shouldn't need a special case for n == 0, but NumPy complains about indexing into a zero-dimensional
    # array a using a[(Ellipsis,)].
    if n == 0:
        return fn(*arrs)
    
    full_shape = tuple(np.array([a.shape[:n] for a in arrs]).max(0))
    result = None
    for full_idx in itertools.product(*map(range, full_shape)):
        inputs = [a[broadcast(full_idx, a.shape[:n]) + (Ellipsis,)] for a in arrs]
        curr = fn(*inputs)
        
        if result is None:
            if type(curr) == tuple:
                result = tuple(np.zeros(full_shape + np.asarray(c).shape) for c in curr)
            else:
                result = np.zeros(full_shape + np.asarray(curr).shape)

        if type(curr) == tuple:
            for i, c in enumerate(curr):
                result[i][full_idx + (Ellipsis,)] = c
        else:
            result[full_idx + (Ellipsis,)] = curr
    return result

def extend_slice(slc, n):
    if not isinstance(slc, tuple):
        slc = (slc,)
    if any([isinstance(s, np.ndarray) for s in slc]):
        raise NotImplementedError('Advanced slicing not implemented yet')
    return slc + (slice(None),) * n

def process_slice(slc, shape, n):
    """Takes a slice and returns the appropriate slice into an array that's being broadcast (i.e. by
    converting the appropriate entries to 0's and :'s."""
    if not isinstance(slc, tuple):
        slc = (slc,)
    slc = list(slc)
    ndim = len(shape) - n
    assert ndim >= 0
    shape_idx = 0
    for slice_idx, s in enumerate(slc):
        if s == nax:
            continue
        if shape[shape_idx] == 1:
            if type(s) == int:
                slc[slice_idx] = 0
            else:
                slc[slice_idx] = slice(None)
        shape_idx += 1
    if shape_idx != ndim:
        raise IndexError('Must have %d terms in the slice object' % ndim)
    return extend_slice(tuple(slc), n)

def my_sum(a, axis, count):
    """For an array a which might be broadcast, return the value of a.sum() were a to be expanded out in full."""
    if a.shape[axis] == count:
        return a.sum(axis)
    elif a.shape[axis] == 1:
        return count * a.sum(axis)
    else:
        raise IndexError('Cannot be broadcast: a.shape=%s, axis=%d, count=%d' % (a.shape, axis, count))
        
    

def match_shapes(arrs):
    """Prepend 1's to the shapes so that the dimensions line up."""
    #temp = [(name, np.asarray(a), deg) for name, a, deg in arrs]
    #ndim = max([a.ndim - deg for _, a, deg in arrs])

    temp = [a for name, a, deg in arrs]
    for i in range(len(temp)):
        if np.isscalar(temp[i]):
            temp[i] = np.array(temp[i])
    ndim = max([a.ndim - deg for a, (_, _, deg) in zip(temp, arrs)])

    prep_arrs = []
    for name, a, deg in arrs:
        if np.isscalar(a):
            a = np.asarray(a)
        if a.ndim < deg:
            raise RuntimeError('%s.ndim must be at least %d' % (name, deg))
        if a.ndim < ndim + deg:
            #a = a.reshape((1,) * (ndim + deg - a.ndim) + a.shape)
            slc = (nax,) * (ndim + deg - a.ndim) + (Ellipsis,)
            a = a[slc]
        prep_arrs.append(a)

    return prep_arrs
    
def lstsq(A, b):
    # do this rather than call lstsq to support efficient broadcasting
    P = array_map(np.linalg.pinv, [A], A.ndim - 2)
    return array_map(np.dot, [P, b], A.ndim - 2)

def dot(A, b):
    return array_map(np.dot, [A, b], A.ndim - 2)

def vdot(x, y):
    return (x*y).sum(-1)

def my_inv(A):
    """Compute the inverse of a symmetric positive definite matrix."""
    cho = scipy.linalg.flapack.dpotrf(A)
    choinv = scipy.linalg.flapack.dtrtri(cho[0])
    upper = scipy.linalg.flapack.dlauum(choinv[0])[0]

    # upper is the upper triangular entries of A^{-1}, so need to fill in the
    # lower triangular ones; unfortunately this has nontrivial overhead
    temp = np.diag(upper)
    return upper + upper.T - np.diag(temp)


def transp(A):
    return A.swapaxes(-2, -1)


def get_counts(array, n):
    result = np.zeros(n, dtype=int)
    ans = np.bincount(array)
    result[:ans.size] = ans
    return result


def log_erfc_helper(x):
    p = 0.47047
    a1 = 0.3480242
    a2 = -0.0958798
    a3 = 0.7478556
    t = 1. / (1 + p*x)
    return np.log(a1 * t + a2 * t**2 + a3 * t**3) - x ** 2

def log_erfc(x):
    return np.where(x > 0., log_erfc_helper(x), np.log(2. - np.exp(log_erfc_helper(-x))))

def log_inv_probit(x):
    return log_erfc(-x / np.sqrt(2.)) - np.log(2.)

def inv_probit(x):
    return 0.5 * scipy.special.erfc(-x / np.sqrt(2.))

def log_erfcinv(log_y):
    a = 0.140012
    log_term = log_y + np.log(2 - np.exp(log_y))

    temp1 = 2 / (np.pi * a) + 0.5 * log_term
    temp2 = temp1 ** 2 - log_term / a
    temp3 = np.sqrt(temp2) - temp1
    return np.sign(1. - np.exp(log_y)) * np.sqrt(temp3)

def log_probit(log_p):
    return -np.sqrt(2) * log_erfcinv(log_p + np.log(2))

def probit(p):
    return -np.sqrt(2) * scipy.special.erfcinv(2 * p)


def check_close(a, b):
    if not np.allclose([a], [b]):   # array brackets to avoid an error comparing inf and inf
        if np.isscalar(a) and np.isscalar(b):
            raise RuntimeError('a=%f, b=%f' % (a, b))
        else:
            raise RuntimeError('Off by %f' % np.max(np.abs(a - b)))

COLORS = ['red', 'green', 'yellow', 'blue', 'magenta', 'cyan']

def print_integers_colored(a):
    print '[',
    for ai in a:
        color = COLORS[ai % len(COLORS)]
        print termcolor.colored(str(ai), color, attrs=['bold']),
    print ']'

def pbar(maxval):
    widgets = [progressbar.Percentage(), ' ', progressbar.Bar(), progressbar.ETA()]
    return progressbar.ProgressBar(widgets=widgets, maxval=maxval).start()
