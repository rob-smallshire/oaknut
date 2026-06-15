REM ===============================
REM OPTIMAL LINE BREAKING THROUGH
REM DYNAMIC PROGRAMMING TO MINIMISE
REM RAGGEDNESS OF THE LEFT MARGIN
REM ===============================

at_least_centiseconds% = 2000

maxwidth% = 40
max_num_characters% = 4096
max_num_words% = 512

REM ---- Allocate buffers ----

DIM text% max_num_characters%

DIM wordstart%(max_num_words%)
DIM wordlen%(max_num_words%)
DIM next%(max_num_words%)
DIM cost%(max_num_words%)

cr% = 13
spc% = ASC(" ")

REM ---- Load text into buffer ----
PROCloadtext
words% = words_count%

REM ---- Tokenise buffer into word pointers ----
PROCtokenise
words% = words_count%

REM ---- Run dynamic programming ----
REM Repeat until at least limit centiseconds have elapsed
num_runs% = 0
start% = TIME
REPEAT
PROCdp
elapsed% = TIME - start%
num_runs% = num_runs% + 1
UNTIL elapsed% >= at_least_centiseconds%

REM ---- Reconstruct output ----
PROCoutput
@%=&0002020A : REM Two decimal places
PRINT
PRINT "Mean: ";elapsed% / 100 / num_runs%;" seconds over ";
@%=&0000000A : REM General format
PRINT ;num_runs%;" runs"
END


REM ===============================
REM LOAD TEXT (DATA -> BUFFER)
REM ===============================
DEF PROCloadtext
LOCAL p%, A$, i%, done%

p% = 0
words_count% = 0

RESTORE

done% = FALSE
REPEAT
READ A$
IF A$ = "" THEN done% = TRUE : GOTO 740

FOR i% = 1 TO LEN(A$)
text%?p% = ASC(MID$(A$, i%, 1))
p% = p% + 1
NEXT i%

REM space between lines
text%?p% = 32
p% = p% + 1

UNTIL done%

REM terminate
text%?p% = 13
ENDPROC


REM ===============================
REM TOKENISATION
REM ===============================
DEF PROCtokenise
LOCAL p%, l%

p% = 0
words_count% = 0

done% = FALSE
REPEAT

REM skip spaces
IF text%?p% <> spc% THEN GOTO 1030
REPEAT
p% = p% + 1
UNTIL text%?p% <> spc%

IF text%?p% = 13 THEN done%=TRUE: GOTO 1180

wordstart%(words_count%) = p%
l% = 0

IF text%?(p% + l%) <= spc% GOTO 1130
REPEAT
l% = l% + 1
UNTIL text%?(p% + l%) <= 32

wordlen%(words_count%) = l%

words_count% = words_count% + 1
p% = p% + l%

UNTIL done%
ENDPROC


REM ===============================
REM DYNAMIC PROGRAMMING
REM ===============================
DEF PROCdp
LOCAL i%, j%, k%, width%, best%, cost%

REM Reinitialise to allow multiple runs
FOR i% = 0 TO max_num_words% - 1
cost%(i%) = 0
next%(i%) = 0
NEXT

FOR i% = words_count% - 1 TO 0 STEP -1

best% = 1000000
width% = 0

FOR j% = i% TO words_count% - 1

REM add word length
IF j% > i% width% = width% + 1
width% = width% + wordlen%(j%)

IF width% > maxwidth% THEN GOTO 1550

REM cost = raggedness + future cost
spare% = maxwidth% - width%
cost% = spare% * spare% + cost%(j% + 1)

IF cost% < best% THEN best% = cost% : next%(i%) = j% + 1

NEXT j%

cost%(i%) = best%

NEXT i%
ENDPROC


REM ===============================
REM OUTPUT RECONSTRUCTION
REM ===============================
DEF PROCoutput
LOCAL i%, j%, k%, c%
CLS
i% = 0

REPEAT

j% = next%(i%)

REM build line in-place
FOR k% = i% TO j% - 1

IF k% > i% THEN VDU spc%

FOR c% = 0 TO wordlen%(k%) - 1
VDU text%?(wordstart%(k%) + c%)
NEXT c%

NEXT k%
IF POS <> 0: PRINT

i% = j%

UNTIL i% = words_count%
ENDPROC


REM ===============================
REM SAMPLE TEXT (HHGTTG)
REM ===============================
DATA "In the beginning the Universe was created."

DATA "This has made a lot of people very angry and been widely regarded as a bad move."

DATA "Many races believe that it was created by some sort of god, though the Jatravartid people of Viltvodle VI believe that the entire Universe was in fact sneezed out of the nose of a being called the Great Green Arkleseizure."

DATA "The Jatravartids, who live in perpetual fear of the time they call the Coming of the Great White Handkerchief, are small blue creatures with more than fifty arms each, "
DATA "who are therefore unique in being the only race in history to have invented the aerosol deodorant before the wheel."

DATA "However, the Great Green Arkleseizure Theory is not widely accepted outside Viltvodle VI and so, the Universe being the puzzling place it is, other explanations are constantly being sought."

DATA ""