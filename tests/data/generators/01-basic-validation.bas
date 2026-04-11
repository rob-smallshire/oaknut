10 REM ====================================================================
20 REM Test Image Generator: Basic Validation
30 REM ====================================================================
40 REM
50 REM Target Format: 80T SSD (Single-sided, 80 tracks)
60 REM Output File:   tests/data/images/01-basic-validation.ssd
70 REM
80 REM Purpose:
90 REM   Create a simple disk with various file types for basic validation
100 REM   of oaknut-dfs reading capabilities.
110 REM   Uses *DIR to change directories before creating files.
120 REM
130 REM Contents:
140 REM   - Text files with known content
150 REM   - Binary data with sequential bytes
160 REM   - Files in different directories ($, A, B)
170 REM   - Mix of locked and unlocked files
180 REM   - Various filename lengths (1-7 characters)
190 REM   - Files with specific load/exec addresses
200 REM
210 REM Expected Validation:
220 REM   - All files readable with correct content
230 REM   - File metadata (load/exec/locked) preserved
240 REM   - Directory structure correct
250 REM ====================================================================
260 :
270 REM Initialize
280 error%=FALSE
290 ON ERROR IF error% THEN END ELSE error%=TRUE:GOTO 1860
300 *DRIVE 0
310 PRINT "Creating basic validation test disk..."
320 PRINT
330 :
340 REM Set disk title
350 *TITLE BASIC TEST
360 :
370 REM ====================================================================
380 REM Section 1: Simple text files in $ directory
390 REM ====================================================================
400 :
410 PRINT "Creating text files..."
420 :
430 REM Short text file
440 file%=OPENOUT("TEXT")
450 text$="Simple text content"
460 FOR I%=1 TO LEN(text$)
470   BPUT#file%,ASC(MID$(text$,I%,1))
480 NEXT I%
490 CLOSE#file%
500 PRINT "  $.TEXT created"
510 :
520 REM Multi-line text file
530 file%=OPENOUT("MULTI")
540 text$="Line 1"+CHR$(13)+CHR$(10)+"Line 2"+CHR$(13)+CHR$(10)+"Line 3"
550 FOR I%=1 TO LEN(text$)
560   BPUT#file%,ASC(MID$(text$,I%,1))
570 NEXT I%
580 CLOSE#file%
590 PRINT "  $.MULTI created"
600 :
610 REM File with 1-character name
620 file%=OPENOUT("X")
630 text$="Short name"
640 FOR I%=1 TO LEN(text$)
650   BPUT#file%,ASC(MID$(text$,I%,1))
660 NEXT I%
670 CLOSE#file%
680 PRINT "  $.X created"
690 :
700 REM File with 7-character name (maximum)
710 file%=OPENOUT("ABCDEFG")
720 text$="Seven character filename test"
730 FOR I%=1 TO LEN(text$)
740   BPUT#file%,ASC(MID$(text$,I%,1))
750 NEXT I%
760 CLOSE#file%
770 PRINT "  $.ABCDEFG created"
780 :
790 REM ====================================================================
800 REM Section 2: Binary file with known data pattern
810 REM ====================================================================
820 :
830 PRINT "Creating binary data file..."
840 :
850 REM Create 256 bytes of sequential data (0-255)
860 DIM data% 255
870 FOR I%=0 TO 255
880   data%?I%=I%
890 NEXT I%
900 REM Save with specific load/exec addresses using *SAVE
910 A$="SAVE BINARY "+STR$~(data%)+" +100 2000 2000"
920 OSCLI A$
930 PRINT "  $.BINARY created (load=&2000, exec=&2000)"
940 :
950 REM ====================================================================
960 REM Section 3: Files in directory A
970 REM ====================================================================
980 :
990 PRINT "Creating directory A files..."
1000 *DIR A
1010 :
1020 file%=OPENOUT("DATA1")
1030 text$="Directory A, file 1"
1040 FOR I%=1 TO LEN(text$)
1050   BPUT#file%,ASC(MID$(text$,I%,1))
1060 NEXT I%
1070 CLOSE#file%
1080 PRINT "  A.DATA1 created"
1090 :
1100 file%=OPENOUT("DATA2")
1110 text$="Directory A, file 2"
1120 FOR I%=1 TO LEN(text$)
1130   BPUT#file%,ASC(MID$(text$,I%,1))
1140 NEXT I%
1150 CLOSE#file%
1160 PRINT "  A.DATA2 created"
1170 :
1180 file%=OPENOUT("DATA3")
1190 text$="Directory A, file 3"
1200 FOR I%=1 TO LEN(text$)
1210   BPUT#file%,ASC(MID$(text$,I%,1))
1220 NEXT I%
1230 CLOSE#file%
1240 PRINT "  A.DATA3 created"
1250 :
1260 *DIR $
1270 :
1280 REM ====================================================================
1290 REM Section 4: Files in directory B
1300 REM ====================================================================
1310 :
1320 PRINT "Creating directory B files..."
1330 *DIR B
1340 :
1350 file%=OPENOUT("FILE1")
1360 text$="Directory B, file 1"
1370 FOR I%=1 TO LEN(text$)
1380   BPUT#file%,ASC(MID$(text$,I%,1))
1390 NEXT I%
1400 CLOSE#file%
1410 PRINT "  B.FILE1 created"
1420 :
1430 file%=OPENOUT("FILE2")
1440 text$="Directory B, file 2"
1450 FOR I%=1 TO LEN(text$)
1460   BPUT#file%,ASC(MID$(text$,I%,1))
1470 NEXT I%
1480 CLOSE#file%
1490 PRINT "  B.FILE2 created"
1500 :
1510 *DIR $
1520 :
1530 REM ====================================================================
1540 REM Section 5: Locked file
1550 REM ====================================================================
1560 :
1570 PRINT "Creating locked file..."
1580 :
1590 file%=OPENOUT("LOCKED")
1600 text$="This file is locked and cannot be deleted"
1610 FOR I%=1 TO LEN(text$)
1620   BPUT#file%,ASC(MID$(text$,I%,1))
1630 NEXT I%
1640 CLOSE#file%
1650 *ACCESS LOCKED L
1660 PRINT "  $.LOCKED created and locked"
1670 :
1680 REM ====================================================================
1690 REM Summary
1700 REM ====================================================================
1710 :
1720 PRINT
1730 PRINT "Test disk created successfully!"
1740 PRINT
1750 PRINT "Files created:"
1760 PRINT "  $ directory: TEXT, MULTI, X, ABCDEFG, BINARY, LOCKED"
1770 PRINT "  A directory: DATA1, DATA2, DATA3"
1780 PRINT "  B directory: FILE1, FILE2"
1790 PRINT
1800 PRINT "Total: 11 files"
1810 PRINT
1820 PRINT "Run *CAT to verify catalog"
1830 *DRIVE 0
1840 END
1850 :
1860 REM Error handler
1870 *DRIVE 0
1880 PRINT "Error: ";REPORT$;" at line ";ERL
1890 END
