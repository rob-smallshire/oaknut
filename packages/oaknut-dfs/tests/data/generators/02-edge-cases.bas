10 REM ====================================================================
20 REM Test Image Generator: Edge Cases
30 REM ====================================================================
40 REM
50 REM Target Format: 80T SSD (Single-sided, 80 tracks)
60 REM Output File:   tests/data/images/02-edge-cases.ssd
70 REM
80 REM Purpose:
90 REM   Test boundary conditions and edge cases in DFS handling.
100 REM   Uses *DIR to change directories before creating files.
110 REM
120 REM Contents:
130 REM   - Exactly 31 files (maximum for standard DFS catalog)
140 REM   - Mix of directories to test catalog packing
150 REM   - Special filenames (!BOOT, etc.)
160 REM
170 REM Expected Validation:
180 REM   - Catalog full detection works
190 REM   - All 31 files readable
200 REM   - Special characters in filenames handled
210 REM ====================================================================
220 :
230 REM Initialize
240 error%=FALSE
250 ON ERROR IF error% THEN END ELSE error%=TRUE:GOTO 1350
260 *DRIVE 0
270 PRINT "Creating edge cases test disk..."
280 PRINT
290 :
300 REM Set disk title
310 *TITLE EDGE
320 :
330 REM ====================================================================
340 REM Create exactly 31 files to fill catalog
350 REM ====================================================================
360 :
370 PRINT "Creating 31 files to fill catalog..."
380 PRINT "(This will take a moment...)"
390 PRINT
400 :
410 REM Files 1-10 in $ directory
420 FOR I%=0 TO 9
430   filename$="FILE"+STR$(I%)
440   REM Remove leading space from STR$
450   IF LEFT$(filename$,1)=" " THEN filename$=MID$(filename$,2)
460   file%=OPENOUT(filename$)
470   text$="File number "+STR$(I%)+" in $ directory"
480   FOR J%=1 TO LEN(text$)
490     BPUT#file%,ASC(MID$(text$,J%,1))
500   NEXT J%
510   CLOSE#file%
520   PRINT "  $.";filename$;" created"
530 NEXT I%
540 :
550 REM Files 11-20 in A directory
560 *DIR A
570 FOR I%=10 TO 19
580   filename$="FILE"+STR$(I%)
590   IF LEFT$(filename$,1)=" " THEN filename$=MID$(filename$,2)
600   file%=OPENOUT(filename$)
610   text$="File number "+STR$(I%)+" in A directory"
620   FOR J%=1 TO LEN(text$)
630     BPUT#file%,ASC(MID$(text$,J%,1))
640   NEXT J%
650   CLOSE#file%
660   PRINT "  A.";filename$;" created"
670 NEXT I%
680 *DIR $
690 :
700 REM Files 21-28 in B directory
710 *DIR B
720 FOR I%=20 TO 27
730   filename$="FILE"+STR$(I%)
740   IF LEFT$(filename$,1)=" " THEN filename$=MID$(filename$,2)
750   file%=OPENOUT(filename$)
760   text$="File number "+STR$(I%)+" in B directory"
770   FOR J%=1 TO LEN(text$)
780     BPUT#file%,ASC(MID$(text$,J%,1))
790   NEXT J%
800   CLOSE#file%
810   PRINT "  B.";filename$;" created"
820 NEXT I%
830 *DIR $
840 :
850 REM ====================================================================
860 REM Special filenames (files 29-31)
870 REM ====================================================================
880 :
890 PRINT "Creating special filename files..."
900 :
910 REM !BOOT file (commonly used for auto-boot)
920 file%=OPENOUT("!BOOT")
930 text$="*FX 200,3"+CHR$(13)+CHR$(10)+"*FX 229,1"
940 FOR I%=1 TO LEN(text$)
950   BPUT#file%,ASC(MID$(text$,I%,1))
960 NEXT I%
970 CLOSE#file%
980 PRINT "  $.!BOOT created"
990 :
1000 REM File with hyphen
1010 file%=OPENOUT("TEST-1")
1020 text$="Filename with hyphen"
1030 FOR I%=1 TO LEN(text$)
1040   BPUT#file%,ASC(MID$(text$,I%,1))
1050 NEXT I%
1060 CLOSE#file%
1070 PRINT "  $.TEST-1 created"
1080 :
1090 REM File with number (file 31 - catalog full!)
1100 file%=OPENOUT("FILE31")
1110 text$="This is file 31 - catalog is now full!"
1120 FOR I%=1 TO LEN(text$)
1130   BPUT#file%,ASC(MID$(text$,I%,1))
1140 NEXT I%
1150 CLOSE#file%
1160 PRINT "  $.FILE31 created"
1170 :
1180 REM ====================================================================
1190 REM Summary
1200 REM ====================================================================
1210 :
1220 PRINT
1230 PRINT "Edge cases disk created successfully!"
1240 PRINT
1250 PRINT "Total files: 31 (catalog full)"
1260 PRINT "  $ directory: 10 files + !BOOT + TEST-1 + FILE31"
1270 PRINT "  A directory: 10 files"
1280 PRINT "  B directory: 8 files"
1290 PRINT
1300 PRINT "Run *CAT to verify catalog"
1310 PRINT "Try creating another file - should fail!"
1320 *DRIVE 0
1330 END
1340 :
1350 REM Error handler
1360 *DRIVE 0
1370 PRINT "Error: ";REPORT$;" at line ";ERL
1380 END
