# from dibbs_text_to_code.data_curation_augmentation import data_transformer


# class TestDataTransformer:
#     LOINC_LAB_TEXT_1 = "5-Hydroxytryptophan [Measurement] in Urine"
#     LOINC_LAB_TEXT_2 = "6-oxo-piperidine-2-carboxylate and 6(R+S)-oxo-propylpiperidine-2-carboxylate panel - Urine and Serum or Plasma"
#     LOINC_LAB_TEXT_3 = "This term is intended to collate similar measurements for the LOINC SNOMED CT Collaboration in an ontological view. Additionally, it can be used to communicate a laboratory order, either alone or in combination with specimen or other information in the order. It may NOT be used to report back the measured patient value."

#     def test_get_words(self):
#         text = "HERE patiEnt's my TEST09:blah string       yes  ,crud,blah,test  about-that  "
#         expected_count = 11

#         test_result = data_transformer.get_words(text)

#         assert len(test_result) == expected_count

#         text_remove_commas = "HERE IS my TEST09: string       yes  crudblahtest    "
#         expected_count = 7

#         test_result = data_transformer.get_words(text_remove_commas)

#         assert len(test_result) == expected_count

#         test_result = data_transformer.get_words(self.LOINC_LAB_TEXT_1)
#         expected_count = 4
#         assert len(test_result) == expected_count

#         test_result = data_transformer.get_words(self.LOINC_LAB_TEXT_2)
#         expected_count = 9
#         assert len(test_result) == expected_count

#         test_result = data_transformer.get_words(self.LOINC_LAB_TEXT_3)
#         expected_count = 53
#         assert len(test_result) == expected_count

#         test_result = data_transformer.get_words("")
#         expected_count = 0
#         assert len(test_result) == expected_count

#     def test_get_char_count(self):
#         text = "HERE IS my TEST09: string       yes  ,crud,blah,test    "
#         expected_count = 36
#         test_result = data_transformer.get_char_count(text)
#         assert test_result == expected_count

#         text_less_spaces = "HERE IS my TEST09: string yes  ,crud,blah,test    "
#         test_result = data_transformer.get_char_count(text_less_spaces)
#         assert test_result == expected_count

#         text_no_num_or_colon = "HERE IS my TEST string   yes  ,crud,blah,test    "
#         test_result = data_transformer.get_char_count(text_no_num_or_colon)
#         expected_count = 33
#         assert test_result == expected_count

#         text_empty = ""
#         expected_count = 0
#         test_result = data_transformer.get_char_count(text_empty)
#         assert test_result == expected_count

#     def test_random_word_deletion(self):
#         test_string = "HERE IS my TEST09: string       yes  ,crud,blah,test    "

#         mod_string = data_transformer.random_char_word_deletion(test_string, 1, 5, 2, "word")
#         assert mod_string == test_string

#     def test_random_char_deletion(self):
#         test_string = "HERE IS my TEST09: string     yes  ,crud,blah,test    "

#         mod_string = data_transformer.random_char_word_deletion(test_string, 1, 5, 2, "char")
#         assert mod_string != test_string
