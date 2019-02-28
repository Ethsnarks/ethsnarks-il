import operator
from copy import copy
from os import urandom
from binascii import hexlify
from functools import reduce
from ethsnarks.field import FQ, int_types


class State(object):
	__slots__ = ('_vars', '_lcs', '_values')

	def __init__(self):
		"""
		The state holds all variables and linear combinations used by the program

			- Variables hold a single field element
			- Linear combinations hold a combination of variables

		Linear combinations can be used to combine multiple operations on variables
		into a single statement, whenever a variable is multiplied by a constant
		or two variables (optionally multipled by constants) are added together etc.

		This forms the basis of many optimisations, think of linear combinations as
		temporary variables, where intermediate results which don't require a constraint
		of their own can be calculated, stored and used in the same way as normal variables.

		Each variable or linear combination is addressed by an index, an index can only be
		a linear combination *or* a variable, but none will have the same index as another.

		When writing a function it can accept zero or more inputs, and emit zero or more
		outputs. For example, an `assert` statement takes one or more inputs and emits none,
		an `add` statement takes two or more inputs and emits one output. The inputs can be
		any combination of variables or linear combinations, as can the outputs.

		If a linear combination or variable is unused by any constraints then it has no purpose.
		"""
		self._vars = dict()
		self._lcs = dict()
		self._values = dict()

	def __getitem__(self, idx):
		if isinstance(idx, Variable):
			idx = idx.idx
		# Prefer linear combinations first
		if idx in self._lcs:
			return self._lcs[idx]
		# Otherwise, fall-through to variables
		if idx in self._vars:
			return self._vars[idx]		
		raise KeyError('Variable or Linear Combination not found!')

	def __contains__(self, idx):
		return idx in self._vars or idx in self._lcs

	def value(self, idx):
		"""
		Get the value for an index, doesn't matter if it's a linear combination or a variable
		"""		
		var = self[idx]
		return var.evaluate(self)

	def _random_idx(self):
		# Auto-generate a new random ID for this variable
		while True:
			# Loop until random unused ID has been found
			idx = hexlify(urandom(8))
			if idx not in self:
				return idx

	def var_new(self, idx=None, title=None, value=None):
		if idx is None:
			idx = self._random_idx()
		if idx in self._vars:
			raise RuntimeError("Cannot create duplicate index")
		if idx in self._lcs:
			raise RuntimeError("Cannot override linear combination with a new variable")
		var = Variable(idx, title)
		self._vars[idx] = var
		if value is not None:
			assert isinstance(value, FQ)
			self._values[idx] = value
		return var

	def var_value_set(self, idx, value):
		if isinstance(idx, Variable):
			idx = idx.idx
		if not isinstance(value, FQ):
			if isinstance(value, int_types):
				value = FQ(value)
			else:
				raise TypeError("Value (%r=%r) of type %r is required to be a field element" % (idx, value, type(value)))
		if idx not in self._vars:
			raise RuntimeError('Unknown variable %r' % (idx,))

		self._values[idx] = value

	def var_value_get(self, idx):
		if isinstance(idx, Variable):
			idx = idx.idx
		return self._values[idx]

	def var_get(self, idx):
		return self._vars[idx]

	def lc_create(self, lc, idx=None):
		if idx is None:
			idx = self._random_idx()
		if isinstance(lc, Term):
			# Upgrade a Term to a Linear Combination
			lc = Combination(lc)
		if not isinstance(lc, Combination):
			raise TypeError('Expected Combination, got %r' % (type(lc),))
		if idx in self._vars:
			raise RuntimeError("Cannot create duplicate index")
		if idx in self._lcs:
			raise RuntimeError("Cannot override linear combination with a new variable")
		self._lcs[idx] = lc
		return lc

	def lc_get(self, idx):
		return self._lcs[idx]


class Variable(object):
	__slots__ = ('idx', 'title')

	def __init__(self, idx, title=None):
		self.idx = idx
		self.title = title

	def evaluate(self, state):
		assert isinstance(state, State)
		return state.var_value_get(self.idx)

	def __mul__(self, other):
		# Multiply by constant, constant becomes coefficient
		return Term(self, other)

	def __add__(self, other):
		return Term(self) + other

	def __sub__(self, other):
		return Term(self) - other

	def __neg__(self):
		return Term(self, FQ(-1))


class Term(object):
	__slots__ = ('var', 'coeff')

	def __init__(self, var, coeff=None):
		assert isinstance(var, Variable)
		self.var = var
		if coeff is None:
			coeff = FQ(1)			
		elif isinstance(coeff, int_types):
			coeff = FQ(coeff)
		if not isinstance(coeff, FQ):
			raise TypeError('Coefficient expected to be field element, but got %r' % (type(coeff),))
		self.coeff = coeff

	def __mul__(self, other):
		# Multiply by constant
		assert isinstance(other, int_types + (FQ,))
		return Term(self.var, self.coeff * other)

	def evaluate(self, state):
		assert isinstance(state, State)
		return self.var.evaluate(state) * self.coeff

	def __add__(self, other):
		if isinstance(other, Combination):
			return other + self
		elif isinstance(other, (Term, Variable)):
			if isinstance(other, Variable):
				other = Term(other)
			return Combination(self, other)
		else:
			raise TypeError("Cannot add unknown type: " + repr(other))

	def __sub__(self, other):
		return self + -other

	def __neg__(self):
		return Term(self.var, -self.coeff)


class Combination(object):
	__slots__ = ('terms', 'title')

	def __init__(self, *terms, title=None):
		self.terms = terms
		self.title = title

	def evaluate(self, state):
		assert isinstance(state, State)
		return reduce(operator.add, [term.evaluate(state) for term in self.terms])

	def __iter__(self):
		return iter(self.terms)

	def __mul__(self, other):
		# Multiply by constant
		return Combination(*[term * other for term in self.terms])

	def __add__(self, other):
		if isinstance(other, Combination):
			return Combination(self.terms + other.terms)
		elif isinstance(other, (Variable, Term)):
			if isinstance(other, Variable):
				other = Term(other)
			return Combination(self.terms + [other])
		else:
			raise TypeError('Unknown type for argument: ' + repr(other))

	def __sub__(self, other):
		other_neg = -other
		return self + other_neg

	def __neg__(self):
		return Combination(*[-term for term in self.terms])


class Constraint(object):
	"""
	Of the form `((A * B) - C) == 0`
	Where each of A, B and C are linear combinations
	"""
	def __init__(self, alpha, bravo, charlie):
		self.alpha = alpha
		self.bravo = bravo
		self.charlie = charlie

	def valid(self, state):
		a = self.alpha.evaluate(state)
		b = self.bravo.evaluate(state)
		c = self.charlie.evaluate(state)
		return (a * b) == c
