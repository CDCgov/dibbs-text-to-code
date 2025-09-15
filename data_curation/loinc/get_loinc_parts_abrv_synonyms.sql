SELECT PART_TYPE_NAME.NAME, PART.PART_NUM, PART.PART, PART.NAME, PART.DESCRIPTION, IIf([PART]![PREF_ABRV]<>[PART]![PART],[PART]![PREF_ABRV],"") AS PREF_ABRV, IIf([SYNONYM_TBL]![SYNONYMS]<>[PART]![PART],IIf([SYNONYM_TBL]![SYNONYMS]<>[PART]![PREF_ABRV],[SYNONYM_TBL]![SYNONYMS],""),IIf([SYNONYM_TBL]![SYNONYMS]<>[PART]![PREF_ABRV],[SYNONYM_TBL]![SYNONYMS],"")) AS SYNONYM INTO LOINC_PARTS_ABRV_SYNONYMS
FROM ((PART_TYPE_NAME LEFT JOIN PART ON PART_TYPE_NAME.PART_TYPE = PART.TYPE) LEFT JOIN PART_SYNONYM_LK ON PART.PART_NUM = PART_SYNONYM_LK.PART_NUMBER) LEFT JOIN SYNONYM_TBL ON PART_SYNONYM_LK.SYNONYM_NUMBER = SYNONYM_TBL.SYNONYM_NUM
WHERE (((PART.PART) Not Like "[{]*" And (PART.PART) Not Like "[*]*" And (PART.PART) Not Like "[?]*" And (PART.PART) Not Like "[-]*" And (PART.PART) Not Like "[_]*") AND ((PART_TYPE_NAME.PART_TYPE) In (1,2,3,4,5,6)))
ORDER BY PART_TYPE_NAME.NAME, PART.PART_NUM;

-- Note, after creating the above query in the RELMA Access DB, you will 
-- Want to save the query as a table 
-- Then you can export the table as a text file with | delimiters

-- NOTE: you will have to manually 'find' and remove special characters (ie.  20666|"COMPONENT"|"LP17035-4"|"Allium cepa"|||"Onion"|"Allium salota Dost�l")
-- So far only 1 special character was found (see example above)