from __future__ import print_function
import sys

from .program import Program


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def print_constriant(constraint, state, prefix="\t"):
	eprint(prefix, "A", constraint.a.title or '')
	for term in constraint.a.terms:
		eprint(prefix, "\t$%r * %r = %r" % (term.var.idx, term.coeff, term.evaluate(state)))
		eprint(prefix, "\t\tvalue of %r is %r (negative of %r)" % (term.var.idx, state.value(term.var), -state.value(term.var)))
	eprint()

	eprint(prefix, "B", constraint.b.title or '')
	for term in constraint.b.terms:
		eprint(prefix, "\t$%r * %r = %r" % (term.var.idx, term.coeff, term.evaluate(state)))
		eprint(prefix, "\t\tvalue of %r is %r (negative of %r)" % (term.var.idx, state.value(term.var), -state.value(term.var)))
	eprint()

	eprint(prefix, "C", constraint.c.title or '')
	for term in constraint.c.terms:
		eprint(prefix, "\t$%r * %r = %r" % (term.var.idx, term.coeff, term.evaluate(state)))
		eprint(prefix, "\t\tvalue of %r is %r (negative of %r)" % (term.var.idx, state.value(term.var), -state.value(term.var)))
	eprint()


class Debugger(object):
	def __init__(self, program):
		assert isinstance(program, Program)
		self.program = program

	def trace_command(self, cmd, state):
		cmd.evaluate(state)

		# Then display the command, and all inputs/outputs/auxvars
		stmt = cmd.as_statement()
		eprint(stmt.as_line())
		for idx, val in [(_, state.value(_)) for _ in cmd.inputs]:
			eprint("\tin %r = %r" % (idx, val))
		for idx, val in [(_, state.value(_)) for _ in cmd.outputs]:
			eprint("\tout %r = %r" % (idx, val))
		if cmd.aux:
			for idx, val in [(_, state.value(_)) for _ in cmd.aux]:
				eprint("\taux %r = %r" % (idx, val))

		constraints = cmd.constraints(state)
		if constraints:
			eprint("\tconstraints:")
			for i, const in enumerate(constraints):
				eprint('\t', i, const.valid(state))
				print_constriant(const, state, "\t\t")
		eprint()

	def trace(self):
		state = self.program.state
		commands = self.program.commands
		for cmd in commands:
			self.trace_command(cmd, state)


def debugger_main(argv):
	if len(argv) < 3:
		print("Usage: %s <file.circuit> <file.input>" % (argv[0],))
		return 1

	with open(argv[1], 'r') as circuit_handle:
		program = Program.from_lines(circuit_handle)

	with open(argv[2], 'r') as input_handle:
		inputs = Program.parse_inputs(input_handle)

	program.setup()

	program.set_values(inputs)

	obj = Debugger(program)
	obj.trace()

	return 0


if __name__ == "__main__":
	sys.exit(debugger_main(sys.argv))
