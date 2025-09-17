SELECT
    LOINC_DETAIL_TYPE_1.LOINC_NUM,
    REFERENCE_INFORMATION.DESCRIPTION,
    LOINC.STATUS
FROM
    LOINC
    INNER JOIN (
        (
            (
                LOINC_DETAIL_TYPE_1
                LEFT JOIN PART ON LOINC_DETAIL_TYPE_1.COMPONENTCORE_PN = PART.PART_NUM
            )
            LEFT JOIN PART_REFERENCE_INFO_LK ON PART.PART_NUM = PART_REFERENCE_INFO_LK.PART_NUM
        )
        LEFT JOIN REFERENCE_INFORMATION ON PART_REFERENCE_INFO_LK.REFERENCE_ID = REFERENCE_INFORMATION.ID
    ) ON LOINC.LOINC_NUM = LOINC_DETAIL_TYPE_1.LOINC_NUM
WHERE
    (((REFERENCE_INFORMATION.DESCRIPTION) IS NOT NULL));

-- NOTE: After creating this query in the RELMA ACCESS DB you will then run the query 
-- and export the results as a csv and store that file in the ./data/snoinc_extracts folder
-- with a file name of: loinc_codes_with_part_descriptions