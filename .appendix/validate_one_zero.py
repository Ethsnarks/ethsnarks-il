from copy import copy
from ethsnarks.field import FQ


def validate_one_zero(one, zero, negone):
	# Eliminates the case one=0, zero=1
	if one * zero != zero:
		return False

	# Eliminates the case one=1, zero=1
	if (one - zero) * one != one:
		return False

	if (negone * negone) != one:
		return False

	if (zero - one) * negone != one:
		return False

	return True


rand_args = []
for i in range(-10, 10):
	rand_args.append(FQ(i))

for _ in range(5):
	rand_args.append(FQ.random())


i = 0
for A in rand_args:
	for B in rand_args:
		for C in rand_args:
			if validate_one_zero(A, B, C):
				A_ok = A==1
				B_ok = B==0
				C_ok = C==FQ(-1)
				if A_ok and B_ok and C_ok:
					print(i, 'OK')
				else:
					print(i, 'A=', A, 'B=', B, 'C=', C, A_ok, B_ok, C_ok)
			i += 1
