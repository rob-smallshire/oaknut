10 REM ====================================================================
20 REM Test Image Generator: Double-Sided Disk
30 REM ====================================================================
40 REM
50 REM Target Format: 80T DSD (Double-sided, 80 tracks, interleaved)
60 REM Output File:   tests/data/images/04-double-sided.dsd
70 REM
80 REM Purpose:
90 REM   Test double-sided disk handling, particularly:
100 REM   - Drive switching between sides (*DRIVE 0 and *DRIVE 2)
110 REM   - Track interleaving (physical layout)
120 REM   - Files on both sides
130 REM   - Higher capacity (400 sectors per side = 800 total)
140 REM
150 REM Important: DFS treats double-sided disks as TWO SEPARATE DRIVES:
160 REM   - *DRIVE 0 = Side 0 (first side)
170 REM   - *DRIVE 2 = Side 1 (second side)
180 REM   - Files on different sides are in separate catalogs
190 REM
200 REM Contents:
210 REM   Side 0 (*DRIVE 0):
220 REM     - Small and medium files
230 REM     - Files in $ and A directories
240 REM   Side 1 (*DRIVE 2):
250 REM     - Large files
260 REM     - Files in $ and B directories
270 REM
280 REM Expected Validation:
290 REM   - Both sides readable independently
300 REM   - Correct physical sector offset calculations
310 REM   - Track interleaving preserved
320 REM ====================================================================
330 :
340 REM Initialize
350 error%=FALSE
360 ON ERROR IF error% THEN END ELSE error%=TRUE:GOTO 1800
370 *DRIVE 0
380 PRINT "Creating double-sided disk test..."
390 PRINT
400 :
410 REM ====================================================================
420 REM SIDE 0 (*DRIVE 0) - Small and medium files
430 REM ====================================================================
440 :
450 PRINT "Switching to DRIVE 0 (Side 0)..."
460 *DRIVE 0
470 PRINT
480 :
490 REM Set disk title for side 0
500 *TITLE SIDE0
510 :
520 PRINT "Creating small files on Side 0..."
530 :
540 FOR I%=1 TO 5
550   filename$="SMALL"+STR$(I%)
560   IF LEFT$(filename$,1)=" " THEN filename$=MID$(filename$,2)
570   file%=OPENOUT(filename$)
580   text$="Side 0, small file "+STR$(I%)
590   FOR J%=1 TO LEN(text$)
600     BPUT#file%,ASC(MID$(text$,J%,1))
610   NEXT J%
620   CLOSE#file%
630   PRINT "  [Drive 0] $.";filename$;" created"
640 NEXT I%
650 :
660 PRINT
670 PRINT "Creating medium files on Side 0 (10 sectors each)..."
680 :
690 FOR I%=1 TO 3
700   filename$="MED"+STR$(I%)
710   IF LEFT$(filename$,1)=" " THEN filename$=MID$(filename$,2)
720   file%=OPENOUT(filename$)
730   REM 2560 bytes = 10 sectors
740   FOR J%=0 TO 2559
750     BPUT#file%,I%
760   NEXT J%
770   CLOSE#file%
780   PRINT "  [Drive 0] $.";filename$;" created (10 sectors)"
790 NEXT I%
800 :
810 PRINT
820 PRINT "Creating directory A files on Side 0..."
830 *DIR A
840 :
850 FOR I%=1 TO 5
860   filename$="FILE"+STR$(I%)
870   IF LEFT$(filename$,1)=" " THEN filename$=MID$(filename$,2)
880   file%=OPENOUT(filename$)
890   text$="Side 0, directory A, file "+STR$(I%)
900   FOR J%=1 TO LEN(text$)
910     BPUT#file%,ASC(MID$(text$,J%,1))
920   NEXT J%
930   CLOSE#file%
940   PRINT "  [Drive 0] A.";filename$;" created"
950 NEXT I%
960 *DIR $
970 :
980 REM ====================================================================
990 REM SIDE 1 (*DRIVE 2) - Large files
1000 REM ====================================================================
1010 :
1020 PRINT
1030 PRINT "Switching to DRIVE 2 (Side 1)..."
1040 *DRIVE 2
1050 PRINT
1060 :
1070 REM Set disk title for side 1
1080 *TITLE SIDE1
1090 :
1100 PRINT "Creating large files on Side 1 (20 sectors each)..."
1110 :
1120 FOR I%=1 TO 3
1130   filename$="LARGE"+STR$(I%)
1140   IF LEFT$(filename$,1)=" " THEN filename$=MID$(filename$,2)
1150   file%=OPENOUT(filename$)
1160   REM 5120 bytes = 20 sectors
1170   FOR J%=0 TO 5119
1180     BPUT#file%,(I%*16+J%) MOD 256
1190   NEXT J%
1200   CLOSE#file%
1210   PRINT "  [Drive 2] $.";filename$;" created (20 sectors)"
1220 NEXT I%
1230 :
1240 PRINT
1250 PRINT "Creating very large file on Side 1 (50 sectors)..."
1260 :
1270 file%=OPENOUT("HUGE")
1280 REM 12800 bytes = 50 sectors
1290 FOR I%=0 TO 12799
1300   BPUT#file%,I% MOD 256
1310 NEXT I%
1320 CLOSE#file%
1330 PRINT "  [Drive 2] $.HUGE created (50 sectors)"
1340 :
1350 PRINT
1360 PRINT "Creating directory B files on Side 1..."
1370 *DIR B
1380 :
1390 FOR I%=1 TO 5
1400   filename$="FILE"+STR$(I%)
1410   IF LEFT$(filename$,1)=" " THEN filename$=MID$(filename$,2)
1420   file%=OPENOUT(filename$)
1430   text$="Side 1, directory B, file "+STR$(I%)
1440   FOR J%=1 TO LEN(text$)
1450     BPUT#file%,ASC(MID$(text$,J%,1))
1460   NEXT J%
1470   CLOSE#file%
1480   PRINT "  [Drive 2] B.";filename$;" created"
1490 NEXT I%
1500 *DIR $
1510 :
1520 REM ====================================================================
1530 REM Summary
1540 REM ====================================================================
1550 :
1560 PRINT
1570 PRINT "Double-sided disk created successfully!"
1580 PRINT
1590 PRINT "SIDE 0 (Drive 0):"
1600 PRINT "  $ directory: SMALL1-SMALL5, MED1-MED3"
1610 PRINT "  A directory: FILE1-FILE5"
1620 PRINT "  Total: 13 files"
1630 PRINT
1640 PRINT "SIDE 1 (Drive 2):"
1650 PRINT "  $ directory: LARGE1-LARGE3, HUGE"
1660 PRINT "  B directory: FILE1-FILE5"
1670 PRINT "  Total: 9 files"
1680 PRINT
1690 PRINT "To verify:"
1700 PRINT "  *DRIVE 0"
1710 PRINT "  *CAT"
1720 PRINT "  *DRIVE 2"
1730 PRINT "  *CAT"
1740 PRINT
1750 PRINT "Note: Each side has its own catalog"
1760 PRINT "      oaknut-dfs must handle both independently"
1770 *DRIVE 0
1780 END
1790 :
1800 REM Error handler
1810 *DRIVE 0
1820 PRINT "Error: ";REPORT$;" at line ";ERL
1830 END
