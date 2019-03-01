import re
import sys
from collections import OrderedDict

from ethsnarks.field import FQ, int_types

from .commands import make_command
from .parser import parse, VariableCount, VariableDeclaration
from .r1cs import State, Constraint


class ProgramError(Exception):
	pass


class Program(object):
	def __init__(self):
		self.commands = list()
		self.total = 0
		self.state = State()
		self.inputs = list()
		self.secrets = list()
		self.outputs = list()

	@classmethod
	def parse_inputs(cls, handle, base=16):
		"""
		Given a file handle containing a mapping of variables to values
		return an ordered dictionary
		"""
		result = OrderedDict()
		for line in handle:
			idx, value = [_.strip() for _ in line.split('=')]
			if value.startswith('0x'):
				base = 16
			elif value.startswith('0b'):
				base = 2
			value = int(value, base)
			result[idx] = value
		return result

	@classmethod
	def from_lines(cls, handle):
		obj = cls()
		obj.parse(handle)
		return obj

	def set_values(self, values):
		for idx, value in values.items():
			self.set_value(idx, value)

	def set_value(self, idx, value):
		if not isinstance(value, FQ):
			if not isinstance(value, int_types):
				raise ProgramError("Value (%r=%r) is of wrong type: %r" % (idx, value, type(value)))
			value = FQ(value)
		if idx not in self.inputs and idx not in self.secrets:
			raise ProgramError("Cannot set a value (%r=%r) that's neither an input nor a secret" % (idx, value))
		self.state.var_value_set(idx, value)

	def value(self, idx):
		"""
		Retrieve the value of a variable
		"""
		return self.state.value(idx)

	def setup(self):
		for cmd in self.commands:
			cmd.setup(self.state)

	def run(self, inputs=None, secrets=None):
		for cmd in self.commands:
			cmd.evaluate(self.state)

	def parse(self, handle, first=True):
		for item in parse(handle):
			if first:
				if not isinstance(item, VariableCount):
					raise ProgramError("First line is required to be 'total'")
				self.total = item.total
				first = False
				continue
			elif isinstance(item, VariableDeclaration):
				if item.is_input:
					self.state.var_new(item.idx)
					self.inputs.append(item.idx)
				elif item.is_output:
					self.outputs.append(item.idx)
				elif item.is_secret:
					self.state.var_new(item.idx)
					self.secrets.append(item.idx)
				else:
					raise ProgramError("Unknown type of variable: %r" % (type(item),))
			else:
				cmd = make_command(item)
				self.commands.append(cmd)


def program_main(argv):
	if len(argv) < 3:
		print("Usage: %s <file.circuit> <file.input>" % (argv[0],))
		return 1

	with open(argv[2], 'r') as input_handle:
		inputs = Program.parse_inputs(input_handle)

	with open(argv[1], 'r') as circuit_handle:		
		program = Program.from_lines(circuit_handle)

	program.setup()

	program.set_values(inputs)

	program.run()

	for idx in program.outputs:
		value = program.value(idx)
		print("%s=%s" % (str(idx), str(value)))

	return 0


if __name__ == "__main__":
	sys.exit(program_main(sys.argv))
