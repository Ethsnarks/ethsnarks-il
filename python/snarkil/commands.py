import operator
from functools import reduce

from ethsnarks.field import FQ

from .r1cs import State, Constraint, Combination, Term
from .parser import AbstractStatement, TableStatement, GenericStatement, ConstMulStatement, Line


class InvalidCommandError(Exception):
    __slots__ = ('stmt', 'line')

    def __init__(self, message, stmt, line=None):
        """
        When constructing a command from a line
        and a statement, it cannot proceed.
        """
        assert isinstance(stmt, AbstractStatement)
        assert isinstance(line, (Line, type(None)))
        self.stmt = stmt
        self.line = line
        super(InvalidCommandError, self).__init__(message)


class AbstractCommand(object):
    __slots__ = ('inputs', 'outputs', 'aux')

    def __init__(self, inputs, outputs, aux=None):
        self.inputs = inputs
        self.outputs = outputs
        self.aux = aux

    def as_statement(self):
        raise NotImplementedError()

    @classmethod
    def from_statement(self, stmt, line=None):
        """
        Returns an instance of AbstractCommand
        """
        assert isinstance(statement, AbstractStatement)
        assert isinstance(line, (Line, type(None)))
        raise NotImplementedError()

    def setup(self, state):
        """
        Setup variables and linear combinations for the circuit
        Required for both evaluation and the constraints
        Performed before either
        """
        assert isinstance(state, State)
        raise NotImplementedError()

    def evaluate(self, state):
        assert isinstance(state, State)
        raise NotImplementedError()

    def constraints(self, state):
        """
        Emits a list of R1CS constraints
        """
        assert isinstance(state, State)
        raise NotImplementedError()


class AbstractBinaryCommand(AbstractCommand):
    __slots__ = ('op',)

    def as_statement(self):
        return GenericStatement(self.term, self.inputs, self.outputs)

    @classmethod
    def from_statement(cls, stmt, line):
        ops = {
            'and': operator.and_,
            'xor': operator.xor,
            'or': operator.or_,
        }
        if stmt.term not in ops:
            raise InvalidCommandError('Unsupported command', stmt, line)
        if len(stmt.in_vars) != 2:
            raise InvalidCommandError('Requires 2 inputs', stmt, line)
        if len(stmt.out_vars) != 1:
            raise InvalidCommandError('Requires 1 output', stmt, line)
        input_A, input_B = stmt.in_vars
        return cls(ops[stmt.term], stmt.in_vars, stmt.out_vars)

    @property
    def term(self):
        raise NotImplementedError()

    def __init__(self, op, inputs, outputs):
        self.op = op
        super(AbstractBinaryCommand, self).__init__(inputs, outputs)

    def setup(self, state):
        # TODO: mark both inputs as required to be binary
        # TOTO: mark output as implicitly binary
        state.var_new(self.outputs[0])

    def evaluate(self, state):
        vals = [int(state.value(_)) for _ in self.inputs]
        for idx, val in zip(self.inputs, vals):
            if val not in [0, 1]:
                raise RuntimeError('Argument %r not binary' % (idx,))
        result = self.op(*vals)
        state.var_value_set(self.outputs[0], result)


class XorBinaryCommand(AbstractBinaryCommand):
    """
    https://github.com/akosba/jsnark/blob/master/JsnarkCircuitBuilder/src/circuit/operations/primitive/XorBasicOp.java
    """
    @property
    def term(self):
        return 'xor'

    def constraints(self, state):
        a = state[self.inputs[0]] * 2
        b = state[self.inputs[1]]
        c = a + b - state[self.outputs[0]]
        return [Constraint(a, b, c)]


class AndBinaryCommand(AbstractBinaryCommand):
    @property
    def term(self):
        return 'and'

    def constraints(self, state):
        a = state[self.inputs[0]]
        b = state[self.inputs[1]]
        c = state[self.outputs[0]]
        return [Constraint(a, b, c)]


class OrBinaryCommand(AbstractBinaryCommand):
    """
    https://github.com/akosba/jsnark/blob/master/JsnarkCircuitBuilder/src/circuit/operations/primitive/ORBasicOp.java
    """

    @property
    def term(self):
        return 'or'

    def constraints(self, state):
        a = state[self.inputs[0]]
        b = state[self.inputs[1]]
        c = a + b - state[self.outputs[0]]
        return [Constraint(a, b, c)]


class AddCommand(AbstractCommand):
    """
    https://github.com/akosba/jsnark/blob/master/JsnarkCircuitBuilder/src/circuit/operations/primitive/AddBasicOp.java
    """

    def as_statement(self):
        return GenericStatement('add', self.inputs, self.outputs)

    @classmethod
    def from_statement(cls, stmt, line):
        if len(stmt.in_vars) < 2:
            raise InvalidCommandError('Requires at least 2 inputs', stmt, line)
        if len(stmt.out_vars) != 1:
            raise InvalidCommandError('Requires 1 output', stmt, line)
        return cls(stmt.in_vars, stmt.out_vars)

    def setup(self, state):
        state.lc_create(self.lc_result(state), self.outputs[0])

    def lc_result(self, state):
        return reduce(operator.add, [state[_] for _ in self.inputs])

    def evaluate(self, state):
        # Evaluation unnecessary, everything is linear constraints
        pass

    def constraints(self, state):
        # Evaluation unnecessary, everything is linear constraints
        pass


class SubCommand(AddCommand):
    def as_statement(self):
        return GenericStatement('sub', self.inputs, self.outputs)

    @property
    def lc_result(self):
        return reduce(operator.sub, [state[_] for _ in self.inputs])


class ConstMulCommand(AbstractCommand):
    __slots__ = ('value', 'is_negative')

    def as_statement(self):
        value = self.value
        term = 'const-mul'
        if self.is_negative:
            term = term + '-neg'
            value = -value
        return ConstMulStatement(value, term, self.inputs, self.outputs)

    @classmethod
    def from_statement(cls, stmt, line):
        if not isinstance(stmt, ConstMulStatement):
            raise InvalidCommandError('Must be ConstMulStatement', stmt, line)

        if len(stmt.in_vars) != 1:
            raise InvalidCommandError('Requires only one input variable', stmt, line)

        if len(stmt.out_vars) != 1:
            raise InvalidCommandError('Requires only one output variable', stmt, line)

        value = stmt.value
        if stmt.is_negative:
            value = -value

        return cls(stmt.in_vars, stmt.out_vars, value, stmt.is_negative)

    def __init__(self, inputs, outputs, value, is_negative):
        self.value = value
        self.is_negative = is_negative
        super(ConstMulCommand, self).__init__(inputs, outputs)

    def setup(self, state):
        result = state[self.inputs[0]] * self.value
        state.lc_create(result, self.outputs[0])

    def evaluate(self, state):
        # Evaluation unnecessary, everything is linear constraints        
        pass

    def constraints(self, state):
        # Evaluation unnecessary, everything is linear constraints
        return []


class NonZeroCheckCommand(AbstractCommand):
    """
    https://github.com/akosba/jsnark/blob/master/JsnarkCircuitBuilder/src/circuit/operations/primitive/NonZeroCheckBasicOp.java
    """

    def as_statement(self):
        return GenericStatement('zerop', self.inputs, self.outputs)

    @classmethod
    def from_statement(cls, stmt, line):
        if len(stmt.in_vars) != 1:
            raise InvalidCommandError('Requires only one input variable', stmt, line)

        if len(stmt.out_vars) != 2:
            raise InvalidCommandError('Requires two output variables', stmt, line)

        return cls(stmt.in_vars, stmt.out_vars)

    def setup(self, state):
        for idx in self.outputs:
            state.var_new(idx)

    def evaluate(self, state):
        input_val = state.value(self.inputs[0])

        # Output value is 1 if input is non-zero, else 0
        result = 0 if input_val == 0 else 1
        state.var_value_set(self.outputs[1], result)

        # Intermediate value 'M'
        state.var_value_set(self.outputs[0], 1/input_val)

    def constraints(self, state):
        """
        Disjunction gadget
        When X is zero, Y will be zero
        When X is non-zero, Y will be 1
        """
        X = state[self.inputs[0]]
        M = state[self.outputs[0]]
        Y = state[self.outputs[1]]
        return [
            #Constraint(Y, Y, Y),
            Constraint(X, state.ONE - Y, state.ZERO),
            Constraint(X, M, Y),
        ]


class AssertCommand(AbstractCommand):
    """
    https://github.com/akosba/jsnark/blob/master/JsnarkCircuitBuilder/src/circuit/operations/primitive/AssertBasicOp.java
    """

    def as_statement(self):
        return GenericStatement('assert', self.inputs, self.outputs)

    @classmethod
    def from_statement(cls, stmt, line):
        if len(stmt.out_vars) != 1:
            raise InvalidCommandError('Requires only one output variable', stmt, line)

        if len(stmt.in_vars) != 2:
            raise InvalidCommandError('Requires two input variables', stmt, line)

        return cls(stmt.in_vars, stmt.out_vars)

    def evaluate(self, state):
        a = state.value(self.inputs[0])
        b = state.value(self.inputs[1])
        c = state.value(self.outputs[0])

        if (a * b) != c:
            raise RuntimeError("Assertion failed!")

    def constraints(self, state):
        return [Constraint(self.inputs[0], self.inputs[1], self.outputs[0])]


class PackCommand(AbstractCommand):
    """
    https://github.com/akosba/jsnark/blob/master/JsnarkCircuitBuilder/src/circuit/operations/primitive/PackBasicOp.java
    """

    def as_statement(self):
        return GenericStatement('pack', self.inputs, self.outputs)

    @classmethod
    def from_statement(cls, stmt, line):
        if len(stmt.out_vars) != 1:
            raise InvalidCommandError('Requires only one output variable', stmt, line)

        if len(stmt.in_vars) == 0:
            raise InvalidCommandError('Requires at least one input variable', stmt, line)

        return cls(stmt.in_vars, stmt.out_vars)

    def setup(self, state):
        state.var_new(self.outputs[0])

    def evaluate(self, state):
        result = self.lc_result(state).evaluate(state)
        state.var_value_set(self.outputs[0], result)

    def lc_result(self, state):
        powers = [2**_ for _ in range(len(self.inputs))]
        terms = [self.state[idx] * p
                 for idx, p in zip(self.inputs, powers)]
        return Combination(*terms)

    def constraints(self, state):
        return [Constraint(self.lc_result(state), 1, self.outputs[0])]


class SplitCommand(AbstractCommand):
    """
    https://github.com/akosba/jsnark/blob/master/JsnarkCircuitBuilder/src/circuit/operations/primitive/SplitBasicOp.java
    """

    def as_statement(self):
        return GenericStatement('split', self.inputs, self.outputs)

    @classmethod
    def from_statement(cls, stmt, line):
        if len(stmt.in_vars) != 1:
            raise InvalidCommandError('Requires only one input variable', stmt, line)

        if len(stmt.out_vars) == 0:
            raise InvalidCommandError('Requires at least one output variable', stmt, line)

        return cls(stmt.in_vars, stmt.out_vars)

    def setup(self, state):
        for idx in self.outputs:
            state.var_new(idx)

    def evaluate(self, state):
        value = state.value(self.inputs[0])
        for i in range(len(self.outputs)):
            bit_value = value & (2**i)
            out_val = 1 if bit_value != 0 else 0
            state.var_value_set(self.outputs[i], out_val)


class MulCommand(AbstractCommand):
    """
    https://github.com/akosba/jsnark/blob/master/JsnarkCircuitBuilder/src/circuit/operations/primitive/MulBasicOp.java
    """

    def as_statement(self):
        return GenericStatement('mul', self.inputs, self.outputs)

    @classmethod
    def from_statement(cls, stmt, line):
        if len(stmt.out_vars) != 1:
            raise InvalidCommandError('Requires only one output variable', stmt, line)

        if len(stmt.in_vars) < 2:
            raise InvalidCommandError('Requires at least two input variables', stmt, line)

        return cls(stmt.in_vars, stmt.out_vars)

    def setup(self, state):
        self.aux = []
        if len(self.inputs) > 2:
            # Allocate one extra auxilliary variable to
            # store intermediate results of the product
            for _ in range(len(self.inputs) - 2):
                self.aux.append(state.var_new())
        state.var_new(self.outputs[0])

    def evaluate(self, state):
        product = state.value(state[self.inputs[0]])
        outputs = self.aux + self.outputs
        for i, idx in enumerate(self.inputs[1:]):
            product = product * state.value(idx)
            state.var_value_set(outputs[i], product)

    def constraints(self, state):
        # [a b c d]
        #   a * b = x
        #   x * c = y
        #   y * d = z
        outputs = self.aux + self.outputs
        result = list()
        it = iter(self.inputs)
        a = state[next(it)]
        for i, b in enumerate(it):
            b = state[b]
            out = state[outputs[i]]
            result.append(Constraint(Term(a), Term(b), Term(out)))
            a = state[outputs[i]]
        return result


class TableCommand(AbstractCommand):
    __slots__ = ('lut',)

    def as_statement(self):
        return TableStatement(self.lut, self.inputs, self.outputs)

    @classmethod
    def cls_for_n_inputs(cls, n_bits, stmt=None, line=None):
        if n_bits > 2:
            return TableCommandNbit
        elif n_bits == 2:
            return TableCommand2bit
        elif n_bits == 1:
            return TableCommand1bit
        else:
            raise InvalidCommandError('Unsupported table with %d bits' % (n_bits,), stmt, line)

    @classmethod
    def from_statement(cls, stmt, line):
        if not isinstance(stmt, TableStatement):
            raise InvalidCommandError('Must be TableStatement', stmt, line)

        if len(stmt.out_vars) != 1:
            raise InvalidCommandError('Requires only one output variable', stmt, line)

        # Require 2^n LUT entries, where each input is binary
        lut_n_expected = (2**len(stmt.in_vars))
        if len(stmt.lut) != lut_n_expected:
            raise InvalidCommandError("Lookup table count mismatch, expected %d, got %d" % (lut_n_expected, len(lut)), stmt, line)

        sub_cls = cls.cls_for_n_inputs(len(stmt.in_vars), stmt, line)

        lut = [FQ(int(_)) for _ in stmt.lut]
        return sub_cls(lut, stmt.in_vars, stmt.out_vars)

    def __init__(self, lut, in_vars, out_vars):
        self.lut = lut
        super(TableCommand, self).__init__(in_vars, out_vars)

    def setup(self, state):
        state.var_new(self.outputs[0])

    def evaluate(self, state):
        idx = 0
        for i, var_idx in enumerate(self.inputs):
            value = int(state.value(var_idx))
            if value not in [0, 1]:
                raise RuntimeError("Variable %d expected to be binary" % (var_idx,))
            idx += ((2**i) * value)
        assert idx < len(self.lut)
        result = self.lut[idx]
        state.var_value_set(self.outputs[0], result)


class TableCommand1bit(TableCommand):
    def constraints(self, state):
        one = state.ONE
        b = state[self.inputs[0]]  # input bit
        r = state[self.outputs[0]] # result

        # Linear combination to select from lookup table
        a = state.constant(self.lut[0])
        a += (b*self.lut[1])
        a -= (b*self.lut[0])

        return [Constraint(a, one, r)]


class TableCommand2bit(TableCommand):
    def constraints(self, state):
        c = self.lut
        b = [state[_] for _ in self.inputs]
        r = state[self.outputs[0]]

        # lhs = c[1] - c[0] + (b[1] * (c[3] - c[2] - c[1] + c[0]))
        lhs_bit = b[1] * (c[3] - c[2] - c[1] + c[0])
        lhs = state.constant(c[1] - c[0]) + lhs_bit

        # rhs = -c[0] + r + (b[1] * (-c[2] + c[0]))
        rhs_bit = b[1] * (-c[2] + c[0])
        rhs = state.constant(-c[0]) + r + rhs_bit

        return [Constraint(lhs, b[0], rhs)]


class TableCommandNbit(AbstractCommand):
    __slots__ = ('lut', 'mux_a', 'mux_b')
    def __init__(self, lut, in_vars, out_vars):
        super(TableCommandNbit, self).__init__(in_vars, out_vars)
        self.lut = lut

    def as_statement(self):
        return TableStatement(self.lut, self.inputs, self.outputs)

    def setup(self, state):
        self.aux = []

        half = len(self.lut) // 2
        assert (len(self.lut) % half) == 0

        # This allows for recursive construction for any number of inputs
        sub_cls = TableCommand.cls_for_n_inputs(len(self.inputs) - 1)

        self.aux.append(state.var_new()) # aux 0
        self.mux_a = sub_cls(self.lut[:half], self.inputs[:-1], [self.aux[-1]])

        self.aux.append(state.var_new()) # aux 1
        self.mux_b = sub_cls(self.lut[half:], self.inputs[:-1], [self.aux[-1]])

        self.aux.append(state.var_new()) # aux 2
        self.aux.append(state.var_new()) # aux 3

        state.lc_create(self.aux[2] + self.aux[3], self.outputs[0])

    def evaluate(self, state):
        self.mux_a.evaluate(state)
        aux_0 = state.value(self.aux[0])

        self.mux_b.evaluate(state)
        aux_1 = state.value(self.aux[1])

        b = state.value(self.inputs[-1])
        state.var_value_set(self.aux[2], ((1-b)*aux_0))
        state.var_value_set(self.aux[3], (b*aux_1))

    def constraints(self, state):
        ret = list()
        ret += self.mux_a.constraints(state)
        ret += self.mux_b.constraints(state)

        # Then selector to choose the first or second auxilliary output depending on the third bit
        b = state[self.inputs[-1]]
        aux = [state[_] for _ in self.aux]
        ret += [
            Constraint(aux[0], state.ONE - b, aux[2]),
            Constraint(aux[1], b, aux[3]),
        ]

        return ret


COMMANDS = {
    # Binary Operations
    'xor': XorBinaryCommand,
    'and': AndBinaryCommand,
    'or': OrBinaryCommand,

    # Special 'const-mul' operations
    'const-mul': ConstMulCommand,
    'const-mul-neg': ConstMulCommand,

    # Lookup-table operations
    'table': TableCommand,

    # Other operations
    'add': AddCommand,
    'sub': SubCommand,
    'mul': MulCommand,
    'assert': AssertCommand,
    'zerop': NonZeroCheckCommand,
    'split': SplitCommand,
    'pack': PackCommand,
}


def make_command(stmt, line=None):
    if not isinstance(stmt, AbstractStatement):
        raise InvalidCommandError("Must be AbstractStatement", stmt, line)
    if isinstance(stmt, TableStatement):
        term = 'table'
    elif isinstance(stmt, GenericStatement):
        term = stmt.term
    else:
        raise InvalidCommandError("Unknown statement type: %r" % (type(stmt),), stmt, line)
    if term not in COMMANDS:
        raise InvalidCommandError("Unknown term %r" % (term,), stmt, line)
    return COMMANDS[term].from_statement(stmt, line)
