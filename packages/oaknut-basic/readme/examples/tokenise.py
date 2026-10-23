"""Tokenising and detokenising a BASIC program."""

from oaknut.basic import detokenise, tokenise

program = tokenise('10 PRINT "HELLO"\n20 GOTO 10\n')  # str -> bytes
listing = detokenise(program)  # bytes -> str
assert tokenise(detokenise(program)) == program  # byte-exact
print(program.hex(" "))
print(listing, end="")
