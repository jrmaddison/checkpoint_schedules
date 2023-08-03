from .schedule import CheckpointSchedule, Forward, Reverse, Copy, Move,\
    EndForward, EndReverse, StorageType
from .utils import n_advance

__all__ = ["TwoLevelCheckpointSchedule"]


class TwoLevelCheckpointSchedule(CheckpointSchedule):
    """A two-level mixed periodic/binomial checkpointing schedule.

    Attributes
    ----------
    period : int
        Forward restart checkpoints are stored to disk every `period`
        forward steps in the initial forward calculation.
    binomial_snapshots : int
        The maximum number of additional forward restart
        checkpointing units to use when advancing the adjoint between periodic
        disk checkpoints.
    binomial_storage : StorageType, optional
        The storage to use for the additional forward
        restart checkpoints generated when advancing the adjoint between
        periodic disk checkpoints. Either `'RAM'` or `'disk'`.
    binomial_trajectory : str, optional
        See the `trajectory` constructor argument for :class:`MultistageCheckpointSchedule`.

    Notes
    -----
    This schedule is described in:
        - Gavin J. Pringle, Daniel C. Jones, Sudipta Goswami, Sri Hari Krishna
          Narayanan, and Daniel Goldberg, 'Providing the ARCHER community with
          adjoint modelling tools for high-performance oceanographic and
          cryospheric computation', version 1.1, EPCC, 2016

    and in the supporting information for

        - D. N. Goldberg, T. A. Smith, S. H. K. Narayanan, P. Heimbach, and M.
          Morlighem, 'Bathymetric influences on Antarctic ice-shelf melt
          rates', Journal of Geophysical Research: Oceans, 125(11),
          e2020JC016370, 2020, doi: 10.1029/2020JC016370

    Online, unlimited adjoint calculations permitted.

    """

    def __init__(self, period, binomial_snapshots, *,
                 binomial_storage=StorageType.DISK,
                 binomial_trajectory="maximum"):
        if period < 1:
            raise ValueError("period must be positive")
        if binomial_storage not in [StorageType.RAM, StorageType.DISK]:
            raise ValueError("Invalid storage")

        super().__init__()

        self._period = period
        self._binomial_snapshots = binomial_snapshots
        self._binomial_storage = binomial_storage
        self._trajectory = binomial_trajectory

    def _iterator(self):
        # Forward

        while self._max_n is None:
            if self._max_n is not None:
                # Unexpected finalize
                raise RuntimeError("Invalid checkpointing state")
            n0 = self._n
            n1 = n0 + self._period
            self._n = n1
            yield Forward(n0, n1, True, False, StorageType.DISK)

        yield EndForward()

        while True:
            # Reverse
            while self._r < self._max_n:
                n = self._max_n - self._r - 1
                n0s = (n // self._period) * self._period
                n1s = min(n0s + self._period, self._max_n)
                if self._r != self._max_n - n1s:
                    raise RuntimeError("Invalid checkpointing state")
                del n, n1s

                snapshots = [n0s]
                while self._r < self._max_n - n0s:
                    if len(snapshots) == 0:
                        raise RuntimeError("Invalid checkpointing state")
                    cp_n = snapshots[-1]
                    if cp_n == self._max_n - self._r - 1:
                        snapshots.pop()
                        self._n = cp_n
                        if cp_n == n0s:
                            yield Copy(cp_n, StorageType.DISK, StorageType.FWD_RESTART) # noqa: E501
                        else:
                            yield Move(cp_n, self._binomial_storage, StorageType.FWD_RESTART) # noqa: E501
                    else:
                        self._n = cp_n
                        if cp_n == n0s:
                            yield Copy(cp_n, StorageType.DISK, StorageType.FWD_RESTART) # noqa: E501
                        else:
                            yield Copy(cp_n, self._binomial_storage, StorageType.FWD_RESTART) # noqa: E501

                        n_snapshots = (self._binomial_snapshots + 1
                                       - len(snapshots) + 1)
                        n0 = self._n
                        n1 = n0 + n_advance(self._max_n - self._r - n0,
                                            n_snapshots,
                                            trajectory=self._trajectory)
                        assert n1 > n0
                        self._n = n1
                        yield Forward(n0, n1, False, False, StorageType.FWD_RESTART)  # noqa: E501

                        while self._n < self._max_n - self._r - 1:
                            n_snapshots = (self._binomial_snapshots + 1
                                           - len(snapshots))
                            n0 = self._n
                            n1 = n0 + n_advance(self._max_n - self._r - n0,
                                                n_snapshots,
                                                trajectory=self._trajectory)
                            assert n1 > n0
                            self._n = n1
                            yield Forward(n0, n1, True, False, self._binomial_storage)

                            if len(snapshots) >= self._binomial_snapshots + 1:
                                raise RuntimeError("Invalid checkpointing "
                                                   "state")
                            snapshots.append(n0)

                        if self._n != self._max_n - self._r - 1:
                            raise RuntimeError("Invalid checkpointing state")

                    self._n += 1
                    yield Forward(self._n - 1, self._n, False, True, StorageType.ADJ_DEPS)  # noqa: E501

                    self._r += 1
                    yield Reverse(self._n, self._n - 1, True)

                if self._r != self._max_n - n0s:
                    raise RuntimeError("Invalid checkpointing state")
                if len(snapshots) != 0:
                    raise RuntimeError("Invalid checkpointing state")
            if self._r != self._max_n:
                raise RuntimeError("Invalid checkpointing state")

            # Reset for new reverse

            self._r = 0
            yield EndReverse(False)

    @property
    def is_exhausted(self):
        return False

    def uses_storage_type(self, storage_type):
        """Check if a given storage type is used in this schedule.

        Parameters
        ----------
        storage_type : StorageType
            Given storage type.
        Returns
        -------
        bool
            Whether this schedule uses the given storage type.
        """
        return storage_type == self._binomial_storage

