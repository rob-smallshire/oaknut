10 REM ===============================
20 REM OPTIMAL LINE BREAKING THROUGH
30 REM DYNAMIC PROGRAMMING TO MINIMISE
40 REM RAGGEDNESS OF THE LEFT MARGIN
50 REM ===============================
60 
70 at_least_centiseconds% = 2000
80 
90 maxwidth% = 40
100 max_num_characters% = 4096
110 max_num_words% = 512
120 
130 REM ---- Allocate buffers ----
140 
150 DIM text% max_num_characters%
160 
170 DIM wordstart%(max_num_words%)
180 DIM wordlen%(max_num_words%)
190 DIM next%(max_num_words%)
200 DIM cost%(max_num_words%)
210 
220 cr% = 13
230 spc% = ASC(" ")
240 
250 REM ---- Load text into buffer ----
260 PROCloadtext
270 words% = words_count%
280 
290 REM ---- Tokenise buffer into word pointers ----
300 PROCtokenise
310 words% = words_count%
320 
330 REM ---- Run dynamic programming ----
340 REM Repeat until at least limit centiseconds have elapsed
350 num_runs% = 0
360 start% = TIME
370 REPEAT
380 PROCdp
390 elapsed% = TIME - start%
400 num_runs% = num_runs% + 1
410 UNTIL elapsed% >= at_least_centiseconds%
420 
430 REM ---- Reconstruct output ----
440 PROCoutput
450 @%=&0002020A : REM Two decimal places
460 PRINT
470 PRINT "Mean: ";elapsed% / 100 / num_runs%;" seconds over ";
480 @%=&0000000A : REM General format
490 PRINT ;num_runs%;" runs"
500 END
510 
520 
530 REM ===============================
540 REM LOAD TEXT (DATA -> BUFFER)
550 REM ===============================
560 DEF PROCloadtext
570 LOCAL p%, A$, i%, done%
580 
590 p% = 0
600 words_count% = 0
610 
620 RESTORE
630 
640 done% = FALSE
650 REPEAT
660 READ A$
670 IF A$ = "" THEN done% = TRUE : GOTO 740
680 
690 FOR i% = 1 TO LEN(A$)
700 text%?p% = ASC(MID$(A$, i%, 1))
710 p% = p% + 1
720 NEXT i%
730 
740 REM space between lines
750 text%?p% = 32
760 p% = p% + 1
770 
780 UNTIL done%
790 
800 REM terminate
810 text%?p% = 13
820 ENDPROC
830 
840 
850 REM ===============================
860 REM TOKENISATION
870 REM ===============================
880 DEF PROCtokenise
890 LOCAL p%, l%
900 
910 p% = 0
920 words_count% = 0
930 
940 done% = FALSE
950 REPEAT
960 
970 REM skip spaces
980 IF text%?p% <> spc% THEN GOTO 1030
990 REPEAT
1000 p% = p% + 1
1010 UNTIL text%?p% <> spc%
1020 
1030 IF text%?p% = 13 THEN done%=TRUE: GOTO 1180
1040 
1050 wordstart%(words_count%) = p%
1060 l% = 0
1070 
1080 IF text%?(p% + l%) <= spc% GOTO 1130
1090 REPEAT
1100 l% = l% + 1
1110 UNTIL text%?(p% + l%) <= 32
1120 
1130 wordlen%(words_count%) = l%
1140 
1150 words_count% = words_count% + 1
1160 p% = p% + l%
1170 
1180 UNTIL done%
1190 ENDPROC
1200 
1210 
1220 REM ===============================
1230 REM DYNAMIC PROGRAMMING
1240 REM ===============================
1250 DEF PROCdp
1260 LOCAL i%, j%, k%, width%, best%, cost%
1270 
1280 REM Reinitialise to allow multiple runs
1290 FOR i% = 0 TO max_num_words% - 1
1300 cost%(i%) = 0
1310 next%(i%) = 0
1320 NEXT
1330 
1340 FOR i% = words_count% - 1 TO 0 STEP -1
1350 
1360 best% = 1000000
1370 width% = 0
1380 
1390 FOR j% = i% TO words_count% - 1
1400 
1410 REM add word length
1420 IF j% > i% width% = width% + 1
1430 width% = width% + wordlen%(j%)
1440 
1450 IF width% > maxwidth% THEN GOTO 1550
1460 
1470 REM cost = raggedness + future cost
1480 spare% = maxwidth% - width%
1490 cost% = spare% * spare% + cost%(j% + 1)
1500 
1510 IF cost% < best% THEN best% = cost% : next%(i%) = j% + 1
1520 
1530 NEXT j%
1540 
1550 cost%(i%) = best%
1560 
1570 NEXT i%
1580 ENDPROC
1590 
1600 
1610 REM ===============================
1620 REM OUTPUT RECONSTRUCTION
1630 REM ===============================
1640 DEF PROCoutput
1650 LOCAL i%, j%, k%, c%
1660 CLS
1670 i% = 0
1680 
1690 REPEAT
1700 
1710 j% = next%(i%)
1720 
1730 REM build line in-place
1740 FOR k% = i% TO j% - 1
1750 
1760 IF k% > i% THEN VDU spc%
1770 
1780 FOR c% = 0 TO wordlen%(k%) - 1
1790 VDU text%?(wordstart%(k%) + c%)
1800 NEXT c%
1810 
1820 NEXT k%
1830 IF POS <> 0: PRINT
1840 
1850 i% = j%
1860 
1870 UNTIL i% = words_count%
1880 ENDPROC
1890 
1900 
1910 REM ===============================
1920 REM SAMPLE TEXT (HHGTTG)
1930 REM ===============================
1940 DATA "In the beginning the Universe was created."
1950 
1960 DATA "This has made a lot of people very angry and been widely regarded as a bad move."
1970 
1980 DATA "Many races believe that it was created by some sort of god, though the Jatravartid people of Viltvodle VI believe that the entire Universe was in fact sneezed out of the nose of a being called the Great Green Arkleseizure."
1990 
2000 DATA "The Jatravartids, who live in perpetual fear of the time they call the Coming of the Great White Handkerchief, are small blue creatures with more than fifty arms each, "
2010 DATA "who are therefore unique in being the only race in history to have invented the aerosol deodorant before the wheel."
2020 
2030 DATA "However, the Great Green Arkleseizure Theory is not widely accepted outside Viltvodle VI and so, the Universe being the puzzling place it is, other explanations are constantly being sought."
2040 
2050 DATA ""