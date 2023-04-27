from checkpoint_schedules import hrevolve_sequence
import copy
import time as tm
class Forward():
    """Define the a forward solver.

    """
    def __init__(self, steps):
        self.exp = None
        self.chk_id = None
        self.steps = steps
        self.chk = None

    def advance(self, n_0: int, n_1: int) -> None:
        """Advance the foward equation.

        Parameters
        ----------
        n0
            Initial time step.
        n1
            Final time step.

        """
        print((">"*(n_1-n_0)).rjust(n_1))
        i_n = n_0
        while i_n < n_1:
            i_np1 = i_n + 1
            i_n = i_np1
        self.chk = i_n


class Backward():
    """This object define the a forward solver.

    """
    def __init__(self):
        self.exp = None
        self.sol = None

    def advance(self, n_1: int, n_0: int) -> None:
        """Execute the backward equation.

        Parameters
        ----------
        n1
            Initial time step in reverse state.
        n0
            Final time step in reverse state.

        """
        print("<".rjust(n_1))
        i_n = n_1
        while i_n > n_0:
            i_np1 = i_n - 1
            i_n = i_np1

start = tm.time()         
steps = 100
cvect = (20, 0)
wvect = (0.0, 0.1)
rvect = (0.0, 0.1)
cfwd = 1.0
cbwd = 2.0
hrev_schedule = hrevolve_sequence.hrevolve(steps, cvect, wvect, rvect,
                                           cfwd=cfwd, cbwd=cbwd
                                           )

schedule = list(hrev_schedule)
fwd = Forward(steps)
bwd = Backward()
schedule0 = copy.copy(schedule)

while True:
    schedule0 = iter(schedule0)
    action = next(schedule0)
    if action.type == "Write":
        storage, n_0 = action.index
    elif action.type == "Forward":
        n_0 = action.index[0]
        n_1 = action.index[1]
        fwd.advance(n_0, n_1)
    elif action.type == "Backward":
        n_0 = action.index
        n_1 = n_0 - 1
        bwd.advance(n_0, n_1)
        if action.index == 0:
            break
        

end = tm.time()
# print(end-start)