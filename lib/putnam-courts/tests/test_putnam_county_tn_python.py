# tests/test_putnam_county_tn_python.py
"""
Automated tests for Putnam County TN Python Court Connector
Tests data parsing, validation, compliance, and Django integration
"""
import pytest
import asyncio
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
import tempfile
import os

# Import the connector components
import sys
sys.path.append('/home/elw/Akashik/connector/src/connectors/putnam-county-tn-python')

from connector import (
    PutnamCountyTNConnector,
    CourtCaseModel,
    CivicEntityModel,
    DigitalAssetModel,
    IdentityModel,
    CourtConnectorError,
    PDFParseError,
    ComplianceError,
    DjangoCourtCase,
    CourtConnectorService
)

# === Test Fixtures ===

@pytest.fixture
def sample_case_data():
    """Sample court case data for testing"""
    return {
        "id": "test-case-1",
        "case_number": "2023-CCIV-001",
        "court": "Putnam County Circuit Court",
        "case_type": "Civil",
        "status": "Pending",
        "docket_date": datetime(2023, 7, 13),
        "disposition": "Pending",
        "docket_number": "CCivKnight071326",
        "expenses": 0.0,
        "efile_status": True,
        "plaintiff": "John Smith",
        "defendant": "City of Cookeville",
        "attorney": "Jane Doe, Esq.",
        "judge": "Caroline Knight",
        "docket_location": "Circuit Court Room 1C"
    }

@pytest.fixture
def sample_court_case(sample_case_data):
    """Sample CourtCaseModel for testing"""
    return CourtCaseModel(**sample_case_data)

@pytest.fixture
def sample_civic_entity():
    """Sample CivicEntityModel for testing"""
    return CivicEntityModel(
        id="test-case-1",
        source="Putnam County Circuit Court (TN)",
        timestamp=datetime(2023, 7, 13),
        title="[Civil] 2023-CCIV-001 - Pending",
        content="Civil Case #2023-CCIV-001\nCourt: Putnam County Circuit Court\nJudge: Caroline Knight\nStatus: Pending\nDisposition: Pending\nDocket Number: CCivKnight071326\nDocket Date: 2023-07-13\nE-file Status: Electronic Filing\nPlaintiff: John Smith\nDefendant: City of Cookeville\nAttorney: Jane Doe, Esq.",
        outcomes=["Pending"],
        reliability="high",
        jurisdiction="Putnam County, Tennessee"
    )

@pytest.fixture
def connector():
    """Putnam County TN connector instance"""
    return PutnamCountyTNConnector(timeout=5, max_retries=1)

# === Test Cases ===

class TestCourtCaseModel:
    """Test CourtCaseModel validation"""
    
    def test_valid_case_creation(self, sample_case_data):
        """Test creating a valid court case"""
        case = CourtCaseModel(**sample_case_data)
        assert case.id == "test-case-1"
        assert case.case_number == "2023-CCIV-001"
        assert case.case_type == "Civil"
        assert case.status == "Pending"
        assert case.plaintiff == "John Smith"
        assert case.defendant == "City of Cookeville"
        assert case.judge == "Caroline Knight"
    
    def test_case_type_validation(self, sample_case_data):
        """Test case type validation"""
        # Valid types
        for case_type in ["Civil", "Criminal", "Domestic", "Traffic", "General Sessions"]:
            data = sample_case_data.copy()
            data["case_type"] = case_type
            case = CourtCaseModel(**data)
            assert case.case_type == case_type
        
        # Invalid type
        data = sample_case_data.copy()
        data["case_type"] = "InvalidType"
        with pytest.raises(ValueError):
            CourtCaseModel(**data)
    
    def test_status_validation(self, sample_case_data):
        """Test status validation"""
        valid_statuses = ["Pending", "Scheduled", "Settled", "Dismissed", "JudgeOrder"]
        for status in valid_statuses:
            data = sample_case_data.copy()
            data["status"] = status
            case = CourtCaseModel(**data)
            assert case.status == status
        
        # Invalid status
        data = sample_case_data.copy()
        data["status"] = "InvalidStatus"
        with pytest.raises(ValueError):
            CourtCaseModel(**data)
    
    def test_date_parsing(self, sample_case_data):
        """Test date parsing from string"""
        data = sample_case_data.copy()
        data["docket_date"] = "2023-07-13T00:00:00"
        case = CourtCaseModel(**data)
        assert case.docket_date == datetime(2023, 7, 13)
        
        # Test with timezone
        data["docket_date"] = "2023-07-13T00:00:00Z"
        case = CourtCaseModel(**data)
        assert case.docket_date == datetime(2023, 7, 13)

class TestCivicEntityModel:
    """Test CivicEntityModel validation"""
    
    def test_valid_entity_creation(self, sample_civic_entity):
        """Test creating a valid CivicEntity"""
        entity = CivicEntityModel(**sample_civic_entity.dict())
        assert entity.id == "test-case-1"
        assert entity.source == "Putnam County Circuit Court (TN)"
        assert entity.type == "court_case"
        assert entity.reliability in ["high", "medium", "low"]
        assert entity.jurisdiction == "Putnam County, Tennessee"
    
    def test_reliability_validation(self):
        """Test reliability field validation"""
        for reliability in ["high", "medium", "low"]:
            entity = CivicEntityModel(
                id="test-1",
                source="test",
                timestamp=datetime.utcnow(),
                title="Test",
                content="Test content",
                outcomes=["test"],
                reliability=reliability,
                jurisdiction="Test Jurisdiction"
            )
            assert entity.reliability == reliability
        
        # Invalid reliability
        with pytest.raises(ValueError):
            CivicEntityModel(
                id="test-1",
                source="test",
                timestamp=datetime.utcnow(),
                title="Test",
                content="Test content",
                outcomes=["test"],
                reliability="invalid",
                jurisdiction="Test Jurisdiction"
            )
    
    def test_outcomes_field(self):
        """Test outcomes field"""
        entity = CivicEntityModel(
            id="test-1",
            source="test",
            timestamp=datetime.utcnow(),
            title="Test",
            content="Test content",
            outcomes=["Pending", "Disposed"],
            reliability="high",
            jurisdiction="Test Jurisdiction"
        )
        assert isinstance(entity.outcomes, list)
        assert len(entity.outcomes) == 2
        assert "Pending" in entity.outcomes
        assert "Disposed" in entity.outcomes

class TestPutnamCountyTNConnector:
    """Test Putnam County TN Connector"""
    
    def test_connector_initialization(self, connector):
        """Test connector initialization"""
        assert connector.timeout == 5
        assert connector.max_retries == 1
        assert hasattr(connector, 'session')
        assert len(connector.DOCKET_SECTIONS) == 6
    
    def test_map_to_civic_entity(self, connector, sample_court_case):
        """Test mapping court case to CivicEntity"""
        civic_entity = connector.map_to_civic_entity(sample_court_case)
        
        assert isinstance(civic_entity, CivicEntityModel)
        assert civic_entity.id == sample_court_case.id
        assert civic_entity.source == "Putnam County Circuit Court (TN)"
        assert civic_entity.type == "court_case"
        assert civic_entity.jurisdiction == "Putnam County, Tennessee"
        assert "[Civil]" in civic_entity.title
        assert "2023-CCIV-001" in civic_entity.title
        assert "Pending" in civic_entity.title
        assert civic_entity.content is not None
        assert len(civic_entity.content) > 50
        assert civic_entity.reliability == "high"  # efile_status=True
        assert civic_entity.outcomes == ["Pending"]
    
    def test_map_to_civic_entity_low_reliability(self, connector):
        """Test mapping with low reliability (paper filing)"""
        case_data = {
            "id": "test-case-2",
            "case_number": "2023-CCRM-002",
            "court": "Putnam County Circuit Court",
            "case_type": "Criminal",
            "status": "Scheduled",
            "docket_date": datetime(2023, 7, 30),
            "disposition": "Scheduled",
            "docket_number": "CCriminal073026",
            "expenses": 0.0,
            "efile_status": False,  # Paper filing
            "plaintiff": "State of TN",
            "defendant": "John Doe",
            "attorney": "Public Defender",
            "judge": "William Ridley"
        }
        case = CourtCaseModel(**case_data)
        civic_entity = connector.map_to_civic_entity(case)
        
        assert civic_entity.reliability == "medium"  # Paper filing = medium reliability
    
    def test_validate_compliance_valid_case(self, connector, sample_court_case):
        """Test compliance validation with valid case"""
        is_valid = connector.validate_compliance(sample_court_case)
        assert is_valid is True
    
    def test_validate_compliance_missing_fields(self, connector):
        """Test compliance validation with missing required fields"""
        # Missing case_number
        case_data = {
            "id": "test-case-3",
            "court": "Putnam County Circuit Court",
            "case_type": "Civil",
            "status": "Pending",
            "docket_date": datetime(2023, 7, 13),
            "disposition": "Pending"
        }
        case = CourtCaseModel(**case_data)
        is_valid = connector.validate_compliance(case)
        assert is_valid is False
        
        # Missing docket_date
        case_data = {
            "id": "test-case-4",
            "case_number": "2023-CCIV-002",
            "court": "Putnam County Circuit Court",
            "case_type": "Civil",
            "status": "Pending",
            "disposition": "Pending"
        }
        case = CourtCaseModel(**case_data)
        is_valid = connector.validate_compliance(case)
        assert is_valid is False
    
    def test_validate_compliance_pii_detection(self, connector):
        """Test compliance validation detects PII"""
        # Case with potential SSN
        case_data = {
            "id": "test-case-5",
            "case_number": "2023-CCIV-003",
            "court": "Putnam County Circuit Court",
            "case_type": "Civil",
            "status": "Pending",
            "docket_date": datetime(2023, 7, 13),
            "disposition": "Pending",
            "docket_number": "CCivKnight071327",
            "efile_status": True,
            "plaintiff": "John Smith SSN: 123-45-6789",
            "defendant": "City of Cookeville"
        }
        case = CourtCaseModel(**case_data)
        is_valid = connector.validate_compliance(case)
        assert is_valid is False  # Should fail due to SSN
        
        # Case with driver license
        case_data = {
            "id": "test-case-6",
            "case_number": "2023-CCIV-004",
            "court": "Putnam County Circuit Court",
            "case_type": "Civil",
            "status": "Pending",
            "docket_date": datetime(2023, 7, 13),
            "disposition": "Pending",
            "docket_number": "CCivKnight071328",
            "efile_status": True,
            "plaintiff": "Jane Doe",
            "defendant": "Driver License: TN-123456"
        }
        case = CourtCaseModel(**case_data)
        is_valid = connector.validate_compliance(case)
        assert is_valid is False  # Should fail due to driver license
    
    def test_parse_parties(self, connector):
        """Test party parsing logic"""
        # Standard "v." format
        plaintiff, defendant = connector._parse_parties("John Smith v. City of Cookeville")
        assert plaintiff == "John Smith"
        assert defendant == "City of Cookeville"
        
        # "vs" format
        plaintiff, defendant = connector._parse_parties("State of TN vs. Robert Johnson")
        assert plaintiff == "State of TN"
        assert defendant == "Robert Johnson"
        
        # No match
        plaintiff, defendant = connector._parse_parties("Random statement without parties")
        assert plaintiff == "Unknown Plaintiff"
        assert defendant == "Unknown Defendant"
    
    def test_extract_judge(self, connector):
        """Test judge extraction"""
        # Test various judge formats
        text1 = "Case presided over by Judge Caroline Knight"
        assert connector._extract_judge(text1) == "Caroline Knight"
        
        text2 = "Hearing before J. William Ridley"
        assert connector._extract_judge(text2) == "William Ridley"
        
        text3 = "Before the Court: William Ridley"
        assert connector._extract_judge(text3) == "William Ridley"
        
        text4 = "No judge mentioned here"
        assert connector._extract_judge(text4) is None
    
    def test_format_case_content(self, connector, sample_court_case):
        """Test case content formatting"""
        content = connector._format_case_content(sample_court_case)
        
        assert "Civil Case #2023-CCIV-001" in content
        assert "Court: Putnam County Circuit Court" in content
        assert "Judge: Caroline Knight" in content
        assert "Status: Pending" in content
        assert "Disposition: Pending" in content
        assert "Docket Number: CCivKnight071326" in content
        assert "Docket Date: 2023-07-13" in content
        assert "E-file Status: Electronic Filing" in content
        assert "Plaintiff: John Smith" in content
        assert "Defendant: City of Cookeville" in content
        assert "Attorney: Jane Doe, Esq." in content
    
    @pytest.mark.asyncio
    async def test_fetch_dockets_mock(self, connector):
        """Test fetch_dockets with mocked responses"""
        with patch('requests.Session.get') as mock_get:
            # Mock successful response
            mock_response = Mock()
            mock_response.content = b"%PDF-1.4\n%âãÏÓ\n1 0 obj\n<<\n/Type/Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type/Pages\n/Kids[3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type/Page\n/Parent 2 0 R\n/MediaBox[0 0 612 792]\n>>\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000010 00000 n \n0000000053 00000 n \n0000000102 00000 n \ntrailer\n<<\n/Size 4\n/Root 1 0 R\n>>\nstartxref\n149\n%%EOF"
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            # Mock PDF parsing to return empty list (since we're not actually parsing)
            with patch.object(connector, '_parse_pdf', return_value=[]):
                cases = await connector.fetch_dockets()
                assert isinstance(cases, list)
                # Should have attempted to fetch all sections
                assert mock_get.call_count == len(connector.DOCKET_SECTIONS)
    
    def test_connector_errors(self):
        """Test custom exceptions"""
        # Test base exception
        try:
            raise CourtConnectorError("Base error")
        except CourtConnectorError:
            pass
        
        # Test PDF parse error
        try:
            raise PDFParseError("PDF error")
        except PDFParseError:
            pass
        
        # Test compliance error
        try:
            raise ComplianceError("Compliance error")
        except ComplianceError:
            pass

# === Django Model Tests ===

@pytest.mark.django_db
class TestDjangoModels:
    """Test Django ORM models"""
    
    def test_django_court_case_creation(self):
        """Test creating Django court case"""
        case = DjangoCourtCase.objects.create(
            id="test-case-1",
            case_number="2023-CCIV-001",
            court="Putnam County Circuit Court",
            case_type="Civil",
            status="Pending",
            docket_date=datetime(2023, 7, 13),
            disposition="Pending",
            docket_number="CCivKnight071326"
        )
        
        assert case.id == "test-case-1"
        assert case.case_number == "2023-CCIV-001"
        assert case.case_type == "Civil"
        assert case.status == "Pending"
        assert case.plaintiff is None
        assert case.defendant is None
        assert case.created_at is not None
        assert case.updated_at is not None
    
    def test_django_court_case_str(self):
        """Test string representation"""
        case = DjangoCourtCase.objects.create(
            id="test-case-2",
            case_number="2023-CCRM-002",
            court="Putnam County Circuit Court",
            case_type="Criminal",
            status="Scheduled",
            docket_date=datetime(2023, 7, 30),
            disposition="Scheduled",
            docket_number="CCriminal073026"
        )
        
        # String representation should work
        str_repr = str(case)
        assert "2023-CCRM-002" in str_repr
    
    def test_django_digital_asset_creation(self):
        """Test creating Django digital asset"""
        asset = DjangoDigitalAsset.objects.create(
            source_url="https://example.com/document.pdf",
            file_content="Sample PDF content",
            model_version="1.0.0",
            layer_metadata={"pages": 5, "size": 1024}
        )
        
        assert asset.source_url == "https://example.com/document.pdf"
        assert asset.file_content == "Sample PDF content"
        assert asset.model_version == "1.0.0"
        assert asset.layer_metadata == {"pages": 5, "size": 1024}
    
    def test_django_identity_creation(self):
        """Test creating Django identity"""
        identity = DjangoIdentity.objects.create(
            entity_id="test-entity-1",
            version=1,
            ownership=["user1", "user2"],
            layer_metadata={"source": "court_connector"}
        )
        
        assert identity.entity_id == "test-entity-1"
        assert identity.version == 1
        assert identity.ownership == ["user1", "user2"]
        assert identity.layer_metadata == {"source": "court_connector"}

# === Service Layer Tests ===

@pytest.mark.django_db
class TestCourtConnectorService:
    """Test Django service layer"""
    
    @pytest.mark.asyncio
    async def test_sync_court_cases_empty(self):
        """Test sync with no cases"""
        service = CourtConnectorService()
        
        # Mock connector to return empty list
        with patch.object(service.connector, 'fetch_dockets', return_value=[]):
            results = await service.sync_court_cases()
            
            assert results["fetched"] == 0
            assert results["created"] == 0
            assert results["updated"] == 0
            assert len(results["errors"]) == 0
    
    @pytest.mark.asyncio
    async def test_sync_court_cases_with_data(self):
        """Test sync with sample data"""
        service = CourtConnectorService()
        
        # Mock connector to return sample cases
        sample_cases = [
            CourtCaseModel(
                id="test-case-1",
                case_number="2023-CCIV-001",
                court="Putnam County Circuit Court",
                case_type="Civil",
                status="Pending",
                docket_date=datetime(2023, 7, 13),
                disposition="Pending",
                docket_number="CCivKnight071326",
                expenses=0.0,
                efile_status=True,
                plaintiff="John Smith",
                defendant="City of Cookeville"
            )
        ]
        
        with patch.object(service.connector, 'fetch_dockets', return_value=sample_cases):
            with patch.object(service.connector, 'validate_compliance', return_value=True):
                results = await service.sync_court_cases()
                
                assert results["fetched"] == 1
                assert results["created"] == 1
                assert results["updated"] == 0
                assert len(results["errors"]) == 0
                
                # Verify case was created in database
                assert DjangoCourtCase.objects.count() == 1
                case = DjangoCourtCase.objects.first()
                assert case.case_number == "2023-CCIV-001"
                assert case.case_type == "Civil"
    
    @pytest.mark.asyncio
    async def test_sync_court_cases_compliance_failure(self):
        """Test sync with compliance failure"""
        service = CourtConnectorService()
        
        # Mock connector to return case with PII
        sample_cases = [
            CourtCaseModel(
                id="test-case-pii",
                case_number="2023-CCIV-PII",
                court="Putnam County Circuit Court",
                case_type="Civil",
                status="Pending",
                docket_date=datetime(2023, 7, 13),
                disposition="Pending",
                docket_number="CCivKnight071329",
                expenses=0.0,
                efile_status=True,
                plaintiff="John Smith SSN: 123-45-6789",  # PII
                defendant="City of Cookeville"
            )
        ]
        
        with patch.object(service.connector, 'fetch_dockets', return_value=sample_cases):
            with patch.object(service.connector, 'validate_compliance', return_value=False):
                results = await service.sync_court_cases()
                
                assert results["fetched"] == 1
                assert results["created"] == 0
                assert results["updated"] == 0
                assert len(results["errors"]) == 1
                assert "Compliance failed" in results["errors"][0]
    
    def test_get_cases_by_type(self):
        """Test filtering cases by type"""
        # Create test cases
        DjangoCourtCase.objects.create(
            id="case-1",
            case_number="2023-CCIV-001",
            court="Putnam County Circuit Court",
            case_type="Civil",
            status="Pending",
            docket_date=datetime(2023, 7, 13),
            disposition="Pending",
            docket_number="CCivKnight071326"
        )
        
        DjangoCourtCase.objects.create(
            id="case-2",
            case_number="2023-CCRM-002",
            court="Putnam County Circuit Court",
            case_type="Criminal",
            status="Scheduled",
            docket_date=datetime(2023, 7, 14),
            disposition="Scheduled",
            docket_number="CCriminal073026"
        )
        
        civil_cases = CourtConnectorService().get_cases_by_type("Civil")
        assert len(civil_cases) == 1
        assert civil_cases[0].case_type == "Civil"
        
        criminal_cases = CourtConnectorService().get_cases_by_type("Criminal")
        assert len(criminal_cases) == 1
        assert criminal_cases[0].case_type == "Criminal"
    
    def test_get_cases_by_date_range(self):
        """Test filtering cases by date range"""
        # Create test cases with different dates
        old_case = DjangoCourtCase.objects.create(
            id="old-case",
            case_number="2023-CCIV-001",
            court="Putnam County Circuit Court",
            case_type="Civil",
            status="Pending",
            docket_date=datetime(2023, 6, 13),
            disposition="Pending",
            docket_number="CCivKnight061326"
        )
        
        new_case = DjangoCourtCase.objects.create(
            id="new-case",
            case_number="2023-CCIV-002",
            court="Putnam County Circuit Court",
            case_type="Civil",
            status="Pending",
            docket_date=datetime(2023, 8, 13),
            disposition="Pending",
            docket_number="CCivKnight081326"
        )
        
        # Get cases from July 1 to July 31, 2023
        start_date = datetime(2023, 7, 1)
        end_date = datetime(2023, 7, 31)
        
        cases_in_range = CourtConnectorService().get_cases_by_date_range(start_date, end_date)
        assert len(cases_in_range) == 0  # Neither case falls in range
        
        # Get cases from June 1 to August 31, 2023
        start_date = datetime(2023, 6, 1)
        end_date = datetime(2023, 8, 31)
        
        cases_in_range = CourtConnectorService().get_cases_by_date_range(start_date, end_date)
        assert len(cases_in_range) == 2  # Both cases should be included

# === Integration Tests ===

class TestIntegration:
    """Integration tests for the full system"""
    
    def test_full_mapping_workflow(self, connector, sample_case_data):
        """Test complete workflow from case data to CivicEntity"""
        # Create court case
        case = CourtCaseModel(**sample_case_data)
        
        # Validate compliance
        is_valid = connector.validate_compliance(case)
        assert is_valid is True
        
        # Map to CivicEntity
        civic_entity = connector.map_to_civic_entity(case)
        
        # Validate CivicEntity
        assert civic_entity.id == case.id
        assert civic_entity.source == "Putnam County Circuit Court (TN)"
        assert civic_entity.type == "court_case"
        assert civic_entity.jurisdiction == "Putnam County, Tennessee"
        assert len(civic_entity.content) > 0
        assert civic_entity.reliability == "high"
    
    def test_error_handling_workflow(self, connector):
        """Test error handling in workflow"""
        # Test with invalid case data that should still produce CivicEntity
        invalid_case_data = {
            "id": "invalid-case",
            "court": "",  # Missing required field
            "case_type": "Civil",
            "status": "Pending",
            "docket_date": datetime(2023, 7, 13),
            "disposition": "Pending"
        }
        
        # This should still create a CourtCaseModel (Pydantic will handle validation)
        # But our compliance check should fail
        case = CourtCaseModel(**invalid_case_data)
        is_valid = connector.validate_compliance(case)
        assert is_valid is False  # Missing court field
        
        # Even with invalid data, mapping should still work (with defaults)
        civic_entity = connector.map_to_civic_entity(case)
        assert civic_entity is not None
        assert civic_entity.id == "invalid-case"
        assert civic_entity.source == "Putnam County Circuit Court (TN)"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])