#!/usr/bin/python
"""
This module includes classes and function definitions
provided as part of the H-Revolve python implementation.
The original implementation was developed by authors
Julien Herrmann and Guillaume Aupy and is orignally
distributed under GNU GPL v.3 license terms.

The H-Revolve library is described in detail in the
paper "H-Revolve: A Framework for Adjoint Computation on
Synchronous Hierarchical Platforms" by Herrmann and Pallez [1].

Some minor modifications where made to adapt this libray for the
checkpoint schedules API.

Refs:
[1] Herrmann, Pallez, "H-Revolve: A Framework for
    Adjoint Computation on Synchronous Hierarchical
    Platforms", ACM Transactions on Mathematical
    Software  46(2), 2020.
"""
from .parameters import defaults
from .basic_functions import (Operation as Op, Sequence, Function, argmin)
from functools import partial


def get_hopt_table(lmax, cvect, wvect, rvect, cbwd=2.0, cfwd=1.0, **params):
    """Compute the HOpt table for architecture and l=0...lmax.
    This computation uses a dynamic program.

    Parameters
    ----------
    lmax : int
        Total checkpoint of a forward solver.
    cvect : int
        The number of slots in each level of memory.
    wvect : tuple
        Cost of writing to each level of memory.
    rvect : tuple
        Cost of reading from each level of memory.
    cbwd : float
        Cost of the backward steps.
    cfwd : float
        Cost of the forward steps.

    Notes
    -----
    This function is a copy of the orginal hrevolve_aux
    function that composes the python H-Revolve implementation
    published by Herrmann and Pallez [1].
    Refs:
    [1] Herrmann, Pallez, "H-Revolve: A Framework for
    Adjoint Computation on Synchronous Hierarchical
    Platforms", ACM Transactions on Mathematical
    Software  46(2), 2020.

    Returns
    -------
    tuple(list, list)
        Return optp (?) and opt (?).
    """
    K = len(cvect)
    assert len(wvect) == len(rvect) == len(cvect)
    opt = [[[float("inf")] * (cvect[i] + 1) for _ in range(lmax + 1)] for i in range(K)]
    optp = [[[float("inf")] * (cvect[i] + 1) for _ in range(lmax + 1)] for i in range(K)]
    # Initialize borders of the table
    for k in range(K):
        mmax = cvect[k]
        for m in range(mmax + 1):
            opt[k][0][m] = cbwd
            optp[k][0][m] = cbwd
        for m in range(mmax + 1):
            if (m == 0) and (k == 0):
                continue
            optp[k][1][m] = cfwd + 2 * cbwd + rvect[0]
            opt[k][1][m] = wvect[0] + optp[k][1][m]
    # Fill K = 0
    mmax = cvect[0]
    for l in range(2, lmax):
        optp[0][l][1] = (l + 1) * cbwd + l * (l + 1) / 2 * cfwd + l * rvect[0]
        opt[0][l][1] = wvect[0] + optp[0][l][1]
    for m in range(2, mmax + 1):
        for l in range(2, lmax):
            optp[0][l][m] = min([j * cfwd + opt[0][l - j][m - 1] + rvect[0] + optp[0][j - 1][m] for j in range(1, l)] + [optp[0][l][1]])
            opt[0][l][m] = wvect[0] + optp[0][l][m]
    # Fill K > 0
    for k in range(1, K):
        mmax = cvect[k]
        for l in range(2, lmax):
            opt[k][l][0] = opt[k-1][l][cvect[k-1]]
        for m in range(1, mmax + 1):
            for l in range(1, lmax):
                optp[k][l][m] = min([opt[k-1][l][cvect[k-1]]] + [j * cfwd + opt[k][l - j][m - 1] + rvect[k] + optp[k][j - 1][m] for j in range(1, l)])
                opt[k][l][m] = min(opt[k-1][l][cvect[k-1]], wvect[k] + optp[k][l][m])
    return (optp, opt)


def hrevolve_aux(l, K, cmem, cvect, wvect, rvect, hoptp=None, hopt=None, **params):
    """Auxiliary function of the hrevolve schedule.

    Parameters
    ----------
    l : int
        Total number of the forward step.
    K : int
        The level of memory.
    cmem : int
        Number of available slots in the K-th level of memory.
        E.g., in two level of memory (RAM and Disk), cmem collects 
        the number of checkpoints saved in Disk.
    cvect : tuple
        The number of slots in each level of memory.
    wvect : tuple
        The cost of writing to each level of memory.
    rvect : tuple
        The cost of reading from each level of memory.
    hoptp : _type_, optional
        _description_, by default None
    hopt : _type_, optional
        _description_, by default None
    
    Notes
    -----
    This function is a copy of the orginal hrevolve_aux
    function that composes the python H-Revolve implementation
    published by Herrmann and Pallez [1].
    Refs:
    [1] Herrmann, Pallez, "H-Revolve: A Framework for
    Adjoint Computation on Synchronous Hierarchical
    Platforms", ACM Transactions on Mathematical
    Software  46(2), 2020.
    
    Returns
    -------
    tuple
        Return the optimal sequence of makespan.

    Raises
    ------
    KeyError
        If `cmem = 0`, `hrevolve_aux` should not be call.

    """
    cfwd = params["cfwd"]
    if (hoptp is None) or (hopt is None):
        (hoptp, hopt) = get_hopt_table(l, cvect, wvect, rvect, **params)
    sequence = Sequence(Function("hrevolve_aux", l, [K, cmem]),
                        levels=len(cvect), concat=params["concat"])
    Operation = partial(Op, params=params)
    if cmem == 0:
        raise KeyError("hrevolve_aux should not be call with cmem = 0. Contact developers.")
    if l == 0:
        sequence.insert(Operation("Backward", 0))
        return sequence
    if l == 1:
        if wvect[0] + rvect[0] < rvect[K]:
            sequence.insert(Operation("Write", [0, 0]))
        sequence.insert(Operation("Forward", [0, 1]))
        sequence.insert(Operation("Write_Forward", [0, 1]))
        sequence.insert(Operation("Backward", 1))
        sequence.insert(Operation("Discard_Forward", [0, 1]))
        if wvect[0] + rvect[0] < rvect[K]:
            sequence.insert(Operation("Read", [0, 0]))
        else:
            sequence.insert(Operation("Read", [K, 0]))
        sequence.insert(Operation("Backward", 0))
        sequence.insert(Operation("Discard", [0, 0]))
        return sequence
    if K == 0 and cmem == 1:
        for index in range(l - 1, -1, -1):
            if index != l - 1:
                sequence.insert(Operation("Read", [0, 0]))
            sequence.insert(Operation("Forward", [0, index+1]))
            sequence.insert(Operation("Write_Forward", [0, index+1]))
            sequence.insert(Operation("Backward", index+1))
            sequence.insert(Operation("Discard_Forward", [0, index+1]))
        sequence.insert(Operation("Read", [0, 0]))
        sequence.insert(Operation("Backward", index))
        sequence.insert(Operation("Discard", [0, 0]))
        return sequence
    if K == 0:
        list_mem = [j * cfwd + hopt[0][l - j][cmem - 1] + rvect[0] + hoptp[0][j - 1][cmem] for j in range(1, l)]
        if min(list_mem) < hoptp[0][l][1]:
            jmin = argmin(list_mem)
            sequence.insert(Operation("Forward", [0, jmin]))
            sequence.insert_sequence(
                hrevolve_recurse(l - jmin, 0, cmem - 1, cvect, wvect, rvect,
                                 hoptp=hoptp, hopt=hopt, **params).shift(jmin)
            )
            sequence.insert(Operation("Read", [0, 0]))
            sequence.insert_sequence(
                hrevolve_aux(jmin - 1, 0, cmem, cvect, wvect, rvect,
                             hoptp=hoptp, hopt=hopt, **params)
            )
            return sequence
        else:
            sequence.insert_sequence(
                hrevolve_aux(l, 0, 1, cvect, wvect, rvect, cfwd,
                             hoptp=hoptp, hopt=hopt, **params)
            )
            return sequence
    list_mem = [
        j * cfwd
        + hopt[K][l - j][cmem - 1]
        + rvect[K] + hoptp[K][j - 1][cmem]
        for j in range(1, l)
        ]
    if min(list_mem) < hopt[K-1][l][cvect[K-1]]:
        jmin = argmin(list_mem)
        sequence.insert(Operation("Forward", [0, jmin - 1]))
        sequence.insert_sequence(
            hrevolve_recurse(l - jmin, K, cmem - 1, cvect, wvect, rvect,
                             hoptp=hoptp, hopt=hopt, **params).shift(jmin)
        )
        sequence.insert(Operation("Read", [K, 0]))
        sequence.insert_sequence(
            hrevolve_aux(jmin - 1, K, cmem, cvect, wvect, rvect,
                         hoptp=hoptp, hopt=hopt, **params)
        )
        return sequence
    else:
        sequence.insert_sequence(
            hrevolve_recurse(l, K-1, cvect[K-1], cvect, wvect, rvect,
                             hoptp=hoptp, hopt=hopt, **params)
        )
        return sequence


def hrevolve(l, cvect, wvect, rvect, **params):
    """hrevolve scheduler.
    
    Parameters
    ----------
    l : int
        Number of forward step.
    cvect : tuple
        The number of slots in each level of memory.
    wvect : tuple
        The cost of writing to each level of memory.
    rvect : tuple
        The cost of reading from each level of memory.

    Notes
    -----
    This function is a copy of the orginal hrevolve_aux
    function that composes the python H-Revolve implementation
    published by Herrmann and Pallez [1].
    Refs:
    [1] Herrmann, Pallez, "H-Revolve: A Framework for
    Adjoint Computation on Synchronous Hierarchical
    Platforms", ACM Transactions on Mathematical
    Software  46(2), 2020.

    Returns
    -------
    object
        The optimal sequence of makespan HOpt(l, architecture).
    """
    params["wd"] = wvect
    params["rd"] = rvect
    return hrevolve_recurse(l, len(cvect)-1, cvect[-1], cvect, wvect, rvect,
                            hoptp=None, hopt=None, **params)


def hrevolve_recurse(l, K, cmem, cvect, wvect, rvect, hoptp=None, hopt=None, **params):
    """Hrevolve recurse.

    Parameters
    ----------
    l : int
        Total number of forward step.
    K : int
        The level of memory.
    cmem : int
        Number of available slots in the K-th level of memory.
        In two level of memory (RAM and Disk), `cmem` collects 
        the number of checkpoints saved in Disk.
    cvect : tuple
        The number of slots in each level of memory.
    wvect : tuple
        The cost of writing to each level of memory.
    rvect : tuple
        The cost of reading from each level of memory.
    hoptp : list, optional
        ??, by default None
    hopt : list, optional
        ??, by default None

    Notes
    -----
    This function is a copy of the orginal hrevolve_aux
    function that composes the python H-Revolve implementation
    published by Herrmann and Pallez [1].
    Refs:
    [1] Herrmann, Pallez, "H-Revolve: A Framework for
    Adjoint Computation on Synchronous Hierarchical
    Platforms", ACM Transactions on Mathematical
    Software  46(2), 2020.

    Returns
    -------
    object
        Hrevolve sequence.

    Raises
    ------
    KeyError
        If `K = 0` and `cmem = 0`.
    """
   
    parameters = dict(defaults)
    parameters.update(params)
    if (hoptp is None) or (hopt is None):
        (hoptp, hopt) = get_hopt_table(l, cvect, wvect, rvect, **parameters)
    sequence = Sequence(Function("hrevolve", l, [K, cmem]),
                        levels=len(cvect), concat=parameters["concat"])
    Operation = partial(Op, params=parameters)
    if l == 0:
        sequence.insert(Operation("Backward", 0))
        return sequence
    if K == 0 and cmem == 0:
        raise KeyError("It's impossible to execute an AC graph of size > 0 with no memory.")
    if l == 1:
        sequence.insert(Operation("Write", [0, 0]))
        sequence.insert(Operation("Forward", [0, 1]))
        sequence.insert(Operation("Write_Forward", [0, 1]))
        sequence.insert(Operation("Backward", 1))
        sequence.insert(Operation("Discard_Forward", [0, 1]))
        sequence.insert(Operation("Read", [0, 0]))
        sequence.insert(Operation("Backward", 0))
        sequence.insert(Operation("Discard", [0, 0]))
        return sequence
    if K == 0:
        # first store
        sequence.insert(Operation("Write", [0, 0]))
        sequence.insert_sequence(
            hrevolve_aux(l, 0, cmem, cvect, wvect, rvect,
                         hoptp=hoptp, hopt=hopt, **parameters)
        )
        return sequence
    if wvect[K] + hoptp[K][l][cmem] < hopt[K-1][l][cvect[K-1]]:
        sequence.insert(Operation("Write", [K, 0]))
        sequence.insert_sequence(
            hrevolve_aux(l, K, cmem, cvect, wvect, rvect,
                         hoptp=hoptp, hopt=hopt, **parameters)
        )
        return sequence
    else:
        # ask firtly here and back to this function for K=0
        sequence.insert_sequence(
            hrevolve_recurse(l, K-1, cvect[K-1], cvect, wvect, rvect,
                             hoptp=hoptp, hopt=hopt, **parameters)
        )
        return sequence
