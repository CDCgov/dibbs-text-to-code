<?xml version="1.0" encoding="utf-8" standalone="yes"?>
<!--eCR Data Quality - Text to Code Schematron v 1.0

2025-09 Initial version created - Chuck Hagan-->
<sch:schema xmlns:voc="http://www.lantanagroup.com/voc"
  xmlns:svs="urn:ihe:iti:svs:2008"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xmlns:sdtc="urn:hl7-org:sdtc"
  xmlns="urn:hl7-org:v3"
  xmlns:cda="urn:hl7-org:v3"
  xmlns:sch="http://purl.oclc.org/dsdl/schematron" queryBinding="xslt2">
  <sch:ns prefix="voc" uri="http://www.lantanagroup.com/voc" />
  <sch:ns prefix="svs" uri="urn:ihe:iti:svs:2008" />
  <sch:ns prefix="xsi" uri="http://www.w3.org/2001/XMLSchema-instance" />
  <sch:ns prefix="sdtc" uri="urn:hl7-org:sdtc" />
  <sch:ns prefix="cda" uri="urn:hl7-org:v3" />
  <sch:phase id="text_to_code">
    <sch:active pattern="p-validate_labOrder_ttc"/>
    <sch:active pattern="p-validate_resultObservation_ttc"/>
  </sch:phase>
  <!--  Lab Order-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-->
  <sch:pattern id="p-validate_labOrder_ttc">
    <sch:rule abstract="true" id="r-validate_labOrder_ttc_abstract" role="text_to_code">
      <!--observation code-->
      <sch:assert id="ttc-labOrder-code-missing" test="
        not(cda:code) 
        or cda:code/@code
        or cda:code/cda:translation/@code">Text to Code: Planned observation code data element has no @code attribute</sch:assert>
      <sch:assert id="ttc-labOrder-wrongCode" test="
        not(cda:code/@code or cda:code/cda:translation/@code) 
        or cda:code[@codeSystem = '2.16.840.1.113883.6.1'] 
        or cda:code/cda:translation[@codeSystem = '2.16.840.1.113883.6.1']">Text to Code: Lab Test Name Ordered @codeSystem attribute is not LOINC 2.16.840.1.113883.6.1</sch:assert>
    </sch:rule>
    <sch:rule context="//cda:observation[cda:templateId/@root = '2.16.840.1.113883.10.20.22.4.44']" id="r-validate_labOrder_ttc">
      <sch:extends rule="r-validate_labOrder_ttc_abstract"/>
    </sch:rule>
  </sch:pattern>
  <!--  Lab Result Observation-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-->
  <sch:pattern id="p-validate_resultObservation_ttc">
    <sch:rule abstract="true" id="r-validate_resultObservation_ttc_abstract" role="text_to_code">
      <!--observation code-->
      <sch:assert id="ttc-labTestNameResulted-noCode" test="
        not(cda:code) 
        or cda:code/@code
        or cda:code/cda:translation/@code">Text to Code: Lab Test Name Resulted does not have a @code attribute.</sch:assert>
      <sch:assert id="ttc-labTestNameResulted-wrongCode" test="
        not(cda:code/@code or cda:code/cda:translation/@code)   
        or cda:code[@codeSystem = '2.16.840.1.113883.6.1'] 
        or cda:code/cda:translation[@codeSystem = '2.16.840.1.113883.6.1']">Text to Code: Lab Test Name Resulted code and translation data elements @codeSystem attribute are not LOINC 2.16.840.1.113883.6.1</sch:assert>
      <!--observation value-->
      <sch:assert id="ttc-labTestNameResulted-noCode" test="
        not(cda:value) 
        or cda:value[not(@nullFlavor)]">Text to Code: Lab Result Value is nullFlavor</sch:assert>
      <sch:assert id="ttc-labResultValue-STNoInterp" test="
        (cda:value[@nullFlavor])
        or not(cda:value[@xsi:type='ST']) 
        or cda:interpretationCode">Text to Code: Lab Result Value of type ST does not have an interpretation code</sch:assert>
      <sch:assert id="ttc-labResultValue-PQNoInterp" test="
        (cda:value[@nullFlavor])
        or not(cda:value[@xsi:type='PQ']) 
        or cda:interpretationCode">Text to Code: Lab Result Value of type PQ does not have an interpretation code</sch:assert>
      <sch:assert id="ttc-labResultValue-CDNoCode" test="
        not(cda:value) 
        or cda:value[@nullFlavor]  
        or not(cda:value[@xsi:type='CD']) 
        or cda:value/@code  
        or cda:value/cda:translation/@code
        or cda:interpretationCode">Text to Code: Lab Result Value of type CD does not have a code or an interpretation code</sch:assert>
      <sch:assert id="ttc-labResultValue-CDWrongCodeSystem" test="
        not(cda:value) 
        or cda:value[@nullFlavor]  
        or not(cda:value[@xsi:type='CD']) 
        or not(cda:value/@code or cda:value/cda:translation/@code)  
        or cda:value[@codeSystem = '2.16.840.1.113883.6.96'] 
        or cda:value/cda:translation[@codeSystem = '2.16.840.1.113883.6.96']
        or cda:interpretationCode">Text to Code: Lab result Value of type CD does not have a SNOMED code or an interpretation code</sch:assert>
      <sch:assert id="ttc-labResultInterpretationCode-WrongCodeSystem" test="
        not(cda:interpretationCode) 
        or cda:interpretationCode/@code=document('../schematron/voc_ttc.xml')/voc:systems/voc:system[@valueSetOid='2.16.840.1.113883.1.11.78']/voc:code/@value">Text to Code: Result interpretationCode data element is not in ValueSet Observation Interpretation (HL7)</sch:assert>
    </sch:rule>
    <sch:rule context="//cda:observation[cda:templateId[@root = '2.16.840.1.113883.10.20.22.4.2']]" id="r-validate_resultObservation_ttc">
      <sch:extends rule="r-validate_resultObservation_ttc_abstract"/>
    </sch:rule>
  </sch:pattern>
</sch:schema>