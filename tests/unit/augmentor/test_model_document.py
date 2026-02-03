from src.augmentation.models.document import DocumentType


class TestDocumentModel:
    def test_ecr_data_field(self):
        """Basic unit test for eicr Data Field enum."""
        doc_type_enum = DocumentType
        assert doc_type_enum.EICR.value == "eICR Message"
