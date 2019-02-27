from __future__ import print_function
import re
import sys
from collections import namedtuple


class Line(object):
    __slots__ = ('line_no', 'raw_line', 'term', 'remainder', 'comment')

    def __init__(self, line_no, raw_line, term=None, remainder=None, comment=None):
        self.line_no = line_no
        self.raw_line = raw_line
        self.term = term
        self.remainder = remainder
        self.comment = comment


class ParseError(Exception):
    __slots__ = ('line',)

    def __init__(self, message, line):
        self.line = line
        super().__init__(message)

    def __str__(self):
        # Friendly(er) error messages
        return "on line %d: %s\nLine: '%s'" % (
            self.line.line_no, self.args[0],
            self.line.raw_line.rstrip('\n\r'))


class AbstractStatement(object):
    @classmethod
    def from_line(cls, line):
        """
        Create an instance of the class, from a parsed extended pinocchio format Line
        """
        assert isinstance(line, Line)
        raise NotImplementedError()

    def as_json(self):
        """
        Return the statement suitable for encoding as JSON
        """
        raise NotImplementedError()

    def as_line(self):
        """
        Return the statement in extended pinocchio format
        This is a string
        """
        raise NotImplementedError()


class TableStatement(AbstractStatement):
    __slots__ = ('lut', 'in_vars', 'out_vars')

    def __init__(self, lut, in_vars, out_vars):
        self.lut = lut
        self.in_vars = in_vars
        self.out_vars = out_vars

    @classmethod
    def from_line(cls, line):
        """
        Represents a lookup table
        """
        assert isinstance(line, Line)
        lut, in_vars, out_vars = parse_table(line.remainder, line)
        if len(out_vars) != 1:
            raise ParseError('Requires only one output variable', line)

        # Require 2^n LUT entries, where each input is binary
        lut_n_expected = (2**len(in_vars))
        if len(lut) != lut_n_expected:
            raise ParseError("Lookup table count mismatch, expected %d, got %d" % (lut_n_expected, len(lut)), line)

        return cls(lut, in_vars, out_vars)

    def as_json(self):
        return ['table', self.lut, self.in_vars, self.out_vars]

    def as_line(self):
        return "table %d <%s> in %d <%s> out %d <%s>" % (
            len(self.lut), ' '.join(str(_) for _ in self.lut),
            len(self.in_vars), ' '.join(str(_) for _ in self.in_vars),
            len(self.out_vars), ' '.join(str(_) for _ in self.out_vars))


class GenericStatement(AbstractStatement):
    __slots__ = ('term', 'in_vars', 'out_vars')

    def __init__(self, term, in_vars, out_vars):
        self.term = term
        self.in_vars = in_vars
        self.out_vars = out_vars

    @classmethod
    def from_line(cls, line):
        """
        A binary operation takes two inputs and produces one output.
        Both inputs are expected to be either 1 or 0.
        The output will be either 1 or 0.
        The `operator` parameter is used to calculate the result
        """
        assert isinstance(line, Line)
        in_vars, out_vars = parse_command(line.remainder, line)
        return cls(line.term, in_vars, out_vars)

    def as_json(self):
        return [self.term, self.in_vars, self.out_vars]

    def as_line(self):
        return "%s in %d <%s> out %d <%s>" % (self.term,
            len(self.in_vars), ' '.join(str(_) for _ in self.in_vars),
            len(self.out_vars), ' '.join(str(_) for _ in self.out_vars))


class ConstMulStatement(GenericStatement):
    __slots__ = ('value',)

    def __init__(self, value, term, in_vars, out_vars):
        self.value = value
        super().__init__(term, in_vars, out_vars)

    @classmethod
    def from_line(cls, line):
        assert isinstance(line, Line)
        value, remainder = line.remainder.split(' ', 1)
        value = int(value, 16)
        in_vars, out_vars = parse_command(remainder, line)
        return cls(value, line.term, in_vars, out_vars)

    @property
    def is_negative(self):
        return self.term == 'const-mul-neg'

    def as_json(self):
        return [self.term, self.value, self.in_vars, self.out_vars]

    def as_line(self):
        return "%s-%x in %d <%s> out %d <%s>" % (self.term, self.value,
            len(self.in_vars), ' '.join(str(_) for _ in self.in_vars),
            len(self.out_vars), ' '.join(str(_) for _ in self.out_vars))


class VariableCount(AbstractStatement):
    __slots__ = ('total',)

    def __init__(self, total):
        self.total = total

    @classmethod
    def from_line(cls, line):
        assert isinstance(line, Line)
        splitted = line.remainder.strip().split(' ', 1)
        total = int(splitted[0])
        if len(splitted) > 1 and len(splitted[1]):
            raise ParseError('Remainder after variable count', line)
        return cls(total)

    def as_json(self):
        return ['total', self.total]

    def as_line(self):
        return "total %d" % (self.total,)


class VariableDeclaration(AbstractStatement):
    __slots__ = ('term', 'idx',)

    def __init__(self, term, idx):
        self.term = term
        self.idx = idx

    @classmethod
    def from_line(cls, line):
        assert isinstance(line, Line)
        splitted = line.remainder.strip().split(' ', 1)
        idx = splitted[0]
        if len(splitted) > 1 and len(splitted[1]):
            raise ParseError('Remainder after variable index/name', line)
        return cls(line.term, idx)

    def as_json(self):
        return [self.term, self.idx]

    def as_line(self):
        return "%s %s" % (self.term, str(self.idx))

    @property
    def is_input(self):
        return self.term == 'input'

    @property
    def is_output(self):
        return self.term == 'output'

    @property
    def is_secret(self):
        return self.term == 'nizkinput'


def parse_vars(variable_ids, expected_count, name, line):
    assert isinstance(line, Line)
    variable_ids = variable_ids.split()
    if expected_count:
        expected_count = int(expected_count)
        if len(variable_ids) != expected_count:
            raise ParseError("Could not parse %s, mismatch expected %d got %d" % (
                name, expected_count, len(variable_ids)), line)
    return variable_ids


COMMAND_RX = r'^\s*in\s+((?P<inn>[0-9]+)\s+)?<(?P<in>[^>]+)>\s+out\s+((?P<outn>[0-9]+)\s+)?<(?P<out>[^>]+)>\s*$'

def parse_command(remainder, line):
    """
    Given the remainder of a command, separate it into the input and output variables

    Format:

        in n <...> out n <...>

    or

        in <...> out <...>

    Where each of the 'in' and 'out' are a space separated list of integers representing
    the variable indices.
    """
    assert isinstance(line, Line)
    match = re.match(COMMAND_RX, remainder)
    if not match:
        raise ParseError('Cannot parse command', line)

    in_vars = parse_vars(match.group('in'), match.group('inn'), 'in', line)
    out_vars = parse_vars(match.group('out'), match.group('outn'), 'out', line)

    return in_vars, out_vars


TABLE_RX = r'^\s*((?P<lutn>[0-9]+)\s+)?<(?P<lut>[^>]+)>\s+in\s+((?P<inn>[0-9]+)\s+)?<(?P<in>[^>]+)>\s+out\s+((?P<outn>[0-9]+)\s+)?<(?P<out>[^>]+)>\s*$'

def parse_table(remainder, line):
    """
    Tables are in the form

        table <...> in <...> out <...>

    Or

        table n <...> in n <...> out n <...>

    Where the length specifier (n) for each item is optional

    Where the groups are:

        - lookup table (converted to field elements)
        - input variables
        - output variable(s)

    """
    assert isinstance(line, Line)
    match = re.match(TABLE_RX, remainder)
    if not match:
        raise ParseError('Cannot parse table', line)

    lut = parse_vars(match.group('lut'), match.group('lutn'), 'table', line)
    in_vars = parse_vars(match.group('in'), match.group('inn'), 'in', line)
    out_vars = parse_vars(match.group('out'), match.group('outn'), 'out', line)

    return lut, in_vars, out_vars


SPLIT_LINE_COMMENT_RX = r'^([^#]+)(#.*)?$'

def line_iterator(handle):
    """
    Iterate through the lines
    Comments begin with a hash symbol: #
    Ignores empty lines, or lines which are only a comment
    Emits Line object for each valid line
    """
    for line_no, raw_line in enumerate(handle):
        line = raw_line.strip()

        # Ignore empty lines, or lines which are comments
        if not len(line) or line[0] == '#':
            continue

        # Remove comment from end of line
        m = re.match(SPLIT_LINE_COMMENT_RX, line)
        if not m:
            # Unable to match? Ignore line, it's probably empty
            continue

        # Ignore empty lines (after processing)
        line = m.group(1).strip()
        if not len(line):
            continue

        comment = m.group(2)

        # Split and emit
        term, remainder = line.split(' ', 1)
        term = term.lower()
        remainder = remainder.strip()

        yield Line(line_no, raw_line, term, remainder, comment)


DEFAULT_REPLACEMENTS = [
    # Ordsering matters
    ['const-mul-neg', lambda term, remainder: ('const-mul-neg', term[14:] + ' ' + remainder)],
    ['const-mul', lambda term, remainder: ('const-mul', term[10:] + ' ' + remainder)]
]

DEFAULT_COMMANDS = {
    # I/O Types
    'total': VariableCount,
    'input': VariableDeclaration,
    'output': VariableDeclaration,
    'nizkinput': VariableDeclaration,

    # Binary Operations
    'xor': GenericStatement,
    'and': GenericStatement,    # Equivalent to MUL, but for binary inputs/output
    'or': GenericStatement,

    # Special 'const-mul' operations
    'const-mul': ConstMulStatement,
    'const-mul-neg': ConstMulStatement,

    # Lookup-table operations
    'table': TableStatement,

    # Other operations
    'add': GenericStatement,
    'sub': GenericStatement,
    'mul': GenericStatement,
    'assert': GenericStatement,
    'zerop': GenericStatement,
    'split': GenericStatement,
    'pack': GenericStatement,
}

def parse(handle, commands=None, replacements=None):
    if replacements is None:
        replacements = DEFAULT_REPLACEMENTS

    if commands is None:
        commands = DEFAULT_COMMANDS

    for line in line_iterator(handle):
        # Special cases for const-mul and const-mul-neg, but generic...
        for prefix, handler in replacements:
            if line.term.startswith(prefix):
                line.term, line.remainder = handler(line.term, line.remainder)
                break

        if line.term not in commands:
            raise ParseError('Unknown command', line)

        # Pass `Line` object command, to allow for better error messages
        cmd_type = commands[line.term]
        yield cmd_type.from_line(line)


def parser_main(argv):
    if len(argv) < 2:
        print("Usage: %s <file.circuit>"  % (argv[0],))
        return 1
    with open(argv[1], 'r') as handle:
        for cmd in parse(handle):
            print(cmd.as_line())
    return 0


if __name__ == "__main__":
    sys.exit(parser_main(sys.argv))
