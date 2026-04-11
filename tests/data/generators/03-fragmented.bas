10 REM ====================================================================
20 REM Test Image Generator: Fragmented Disk
30 REM ====================================================================
40 REM
50 REM Target Format: 80T SSD (Single-sided, 80 tracks)
60 REM Output File:   tests/data/images/03-fragmented.ssd
70 REM
80 REM Purpose:
90 REM   Create a disk with intentional fragmentation to test:
100 REM   - Free space calculation
110 REM   - Gap detection between files
120 REM   - Compact operation
130 REM
140 REM Strategy:
150 REM   1. Create files A, B, C, D, E with known sizes
160 REM   2. Delete B and D to create gaps
170 REM   3. Result: A [gap] C [gap] E
180 REM
190 REM Expected Validation:
200 REM   - oaknut-dfs detects gaps correctly
210 REM   - Free space calculation accounts for fragmentation
220 REM   - compact() operation can defragment
230 REM ====================================================================
240 :
250 REM Initialize
260 error%=FALSE
270 ON ERROR IF error% THEN END ELSE error%=TRUE:GOTO 1390
280 *DRIVE 0
290 PRINT "Creating fragmented disk test..."
300 PRINT
310 :
320 REM Set disk title
330 *TITLE FRAGMENT
340 :
350 REM ====================================================================
360 REM Step 1: Create initial files
370 REM ====================================================================
380 :
390 PRINT "Step 1: Creating 5 files..."
400 PRINT
410 :
420 REM File A - 512 bytes (2 sectors)
430 file%=OPENOUT("FILEA")
440 FOR I%=0 TO 511
450   BPUT#file%,65
460 NEXT I%
470 CLOSE#file%
480 PRINT "  $.FILEA created (512 bytes, 2 sectors)"
490 :
500 REM File B - 768 bytes (3 sectors) - WILL BE DELETED
510 file%=OPENOUT("FILEB")
520 FOR I%=0 TO 767
530   BPUT#file%,66
540 NEXT I%
550 CLOSE#file%
560 PRINT "  $.FILEB created (768 bytes, 3 sectors)"
570 :
580 REM File C - 512 bytes (2 sectors)
590 file%=OPENOUT("FILEC")
600 FOR I%=0 TO 511
610   BPUT#file%,67
620 NEXT I%
630 CLOSE#file%
640 PRINT "  $.FILEC created (512 bytes, 2 sectors)"
650 :
660 REM File D - 1024 bytes (4 sectors) - WILL BE DELETED
670 file%=OPENOUT("FILED")
680 FOR I%=0 TO 1023
690   BPUT#file%,68
700 NEXT I%
710 CLOSE#file%
720 PRINT "  $.FILED created (1024 bytes, 4 sectors)"
730 :
740 REM File E - 512 bytes (2 sectors)
750 file%=OPENOUT("FILEE")
760 FOR I%=0 TO 511
770   BPUT#file%,69
780 NEXT I%
790 CLOSE#file%
800 PRINT "  $.FILEE created (512 bytes, 2 sectors)"
810 :
820 PRINT
830 PRINT "Step 1 complete: 5 files created"
840 PRINT
850 :
860 REM ====================================================================
870 REM Step 2: Delete files B and D to create gaps
880 REM ====================================================================
890 :
900 PRINT "Step 2: Deleting FILEB and FILED..."
910 PRINT
920 :
930 *DELETE FILEB
940 PRINT "  $.FILEB deleted (3-sector gap created)"
950 :
960 *DELETE FILED
970 PRINT "  $.FILED deleted (4-sector gap created)"
980 :
990 PRINT
1000 PRINT "Step 2 complete: Gaps created"
1010 PRINT
1020 :
1030 REM ====================================================================
1040 REM Step 3: Create marker file at end
1050 REM ====================================================================
1060 :
1070 PRINT "Step 3: Creating marker file..."
1080 file%=OPENOUT("MARKER")
1090 text$="This file is after the gaps"
1100 FOR I%=1 TO LEN(text$)
1110   BPUT#file%,ASC(MID$(text$,I%,1))
1120 NEXT I%
1130 CLOSE#file%
1140 PRINT "  $.MARKER created"
1150 :
1160 REM ====================================================================
1170 REM Summary
1180 REM ====================================================================
1190 :
1200 PRINT
1210 PRINT "Fragmented disk created successfully!"
1220 PRINT
1230 PRINT "Disk layout (expected sectors):"
1240 PRINT "  Sectors 0-1:   Catalog"
1250 PRINT "  Sectors 2-3:   $.FILEA (2 sectors)"
1260 PRINT "  Sectors 4-6:   [GAP - 3 sectors]"
1270 PRINT "  Sectors 7-8:   $.FILEC (2 sectors)"
1280 PRINT "  Sectors 9-12:  [GAP - 4 sectors]"
1290 PRINT "  Sectors 13-14: $.FILEE (2 sectors)"
1300 PRINT "  Sectors 15+:   $.MARKER (1 sector)"
1310 PRINT
1320 PRINT "Remaining files: 4"
1330 PRINT "Total gaps: 7 sectors"
1340 PRINT
1350 PRINT "Run *CAT to verify"
1360 *DRIVE 0
1370 END
1380 :
1390 REM Error handler
1400 *DRIVE 0
1410 PRINT "Error: ";REPORT$;" at line ";ERL
1420 END
