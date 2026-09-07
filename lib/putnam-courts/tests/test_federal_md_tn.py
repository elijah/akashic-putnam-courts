#!/usr/bin/env python3
"""
Automated tests for Federal Court (Multi-District Tennessee) Connector
Tests federal case parsing, PACER integration, compliance validation
"""
import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import sys

# Import the federal connector components
import sys
sys.path.append('/home/elw/Akashik/connector/src/connectors/federal-md-tn')
from connector import (
    FederalMDTNConnector,
    FederalCaseModel,
    FederalCivicEntityModel,
    PACERClient,
    FederalComplianceError,
    create_federal_connector,
    health_check
)

# === Test Fixtures ===

@pytest.fixture
def sample_federal_case_data():
    """Sample federal case data for testing"""
    return {
        "id": "fed-case-001",
        "case_number": "3:23-cr-00045",
        "court": "US District Court for Middle District of Tennessee",
        "divisions": ["Nashville"],
        "case_type": "Criminal",
        "nature_of_suit": None,
        "offense": None,
        "offense_code": "18",
        "status": "Pending",
        "filed_date": datetime(2023, 6, 15),
        "terminated_date": None,
        "judge": "William L. Campbell, Jr.",
        "magistrate_judge": None,
        "plaintiff": "United States of America",
        "defendant": "John Doe",
        "docket_number": "3:23-cr-00045-WLC",
        "pacer_doc_id": "12345678",
        "cm_ecf_path": "/cfd/mdtn",
        "cm_ecf_doc_id": "87654321",
        "filing_fee": 0.0,
        "has_pdf": True,
        "num_documents": 12
    }

@pytest.fixture
def sample_federal_case(sample_federal_case_data):
    """Sample FederalCaseModel for testing"""
    return FederalCaseModel(**sample_federal_case_data)

@pytest.fixture
def sample_federal_bankruptcy_case():
    """Sample FederalCaseModel for bankruptcy case"""
    return FederalCaseModel(
        id="fed-case-003",
        case_number="3:21-bk-01234",
        court="US Bankruptcy Court for Middle District of Tennessee",
        division="Cookeville",
        case_type="Bankruptcy",
        nature_of_suit=None,
        offense=None,
        status="Closed",
        filed_date=datetime(2021, 11, 30),
        terminated_date=datetime(2022, 2, 15),
        plaintiff="In re: William Johnson",
        docket_number="3:21-bk-01234",
        has_pdf=True,
        num_documents=28,
        filing_fee=335.0
    )

@pytest.fixture
def federal_connector():
    """Federal MDTN connector instance"""
    return FederalMDTNConnector()

# === Validation Tests ===

class TestFederalCaseModel:
    """Test FederalCaseModel validation"""
    
    def test_valid_case_creation(self, sample_federal_case_data):
        """Test creating a valid federal case"""
        case = FederalCaseModel(**sample_federal_case_data)
        assert case.id == "fed-case-001"
        assert case.case_number == "3:23-cr-00045"
        assert case.court == "US District Court for Middle District of Tennessee"
        assert case.division == "Nashville"
        assert case.case_type == "Criminal"
        assert case.status == "Pending"
        assert case.filing_date == datetime(2023, 6, 15)
        assert case.plaintiff == "United States of America"
        assert case.defendant == "John Doe"
        assert case.hass_pdf is True
        assert case.num_documents == 12
    
    def test_case_number_format(self, sample_federal_case):
        """Test case number format validation"""
        case = FederalCaseModel(**sample_federal_case_data)
        assert case.case_number == "3:23-cr-00045"
        # Test pattern validation would go here if implemented
    
    def test_package_attributes_exist(self):
        """Test that required attributes exist"""
        case = FederalCaseModel(
            id="test",
            case_number="1:23-cv-00001",
            court="Test Court",
            division="Test Division",
            case_type("Criminal"),
            status="Pending",
            filed_date=datetime(2023, 1, 1)
        )
        expected_attrs = ["id", "case_number", "court", "case_type", "status", "filed_date"]
        for attr in required_attrs:
            assert hasattr(case, attr)

class TestFederalCivicEntityModel:
    """Test FederalCivicEntityModel validation"""
    
    def test_valid_entity_creation(self):
        """Test creating a valid FederalCivicEntity"""
        content_lines = [
            "Federal Case #3:23-cr-00045",
            "Court: US District Court for Middle District of Tennessee",
            "Content lines here",
            "Filed: 2023-06-15"
        ]
        entity = FederalCivicEntityModel(
            id="fed-case-001",
            source="PACER - Middle District of Tennessee",
            timestamp=datetime(2023, 6, 15),
            title="[Criminal] 3:23-cr-00045 - Pending",
            content="\n".join(content_lines),
            type="federal_case",
            outcomes=["Pending"],
            reliability="high",
            jurisdiction="Federal Court - Middle District of Tennessee"
        )
        assert entity.id == "fed-case-001"
        assert entity.source == "PACER - Middle District of Tennessee"
        assert entity.type == "federal_case"
        assert entity.jurisdiction == "Federal Court - Middle District of Tennessee"
        assert entity.reliability == "high"
    
    def test_reliability_field_validation(self):
        """Test reliability field validation"""
        for reliability in ["high", "medium", "low"]:
            entity = FederalCivicEntityModel(
                id="test",
                source="test",
                timestamp=datetime.utcnow(),
                title="Test",
                content="Test content",
                outcomes=["test"],
                reliability=reliability,
                jurisdiction="Federal Court - Middle District of Tennessee",
                case_type("Criminal"),
                federal_district="MDTN"
            )
            assert entity.reliability == reliability
        
        # Invalid reliability
        with pytest.raises(ValueError):
            FederalCivicEntityModel(
                id="test-invalid",
                source="test",
                timestamp=datetime.utcnow(),
                title="Test",
                content="Test content",
                outcomes=["test"],
                reliability="invalid",
                jurisdiction="Federal Court - Middle District of Tennessee",
                case_type("Criminal"),
                federal_district="MDTN"
            )

class TestFederalMDTNConnector:
    def test_connector_initialization(self):
        """Test connector initialization"""
        connector = FederalMDTNConnector()
        assert len(connector.courthouses) > 0
        assert "Nashville" in connector.courthouses
        assert "Columbia" in connector.courthouses
        assert callable(connector.create_federal_connector)
    
    def test_courthouses_mapping(self):
        """Test courthouse mapping"""
        connector = FederalMDTNConnector()
        expected = {
            "Nashville": "Nashville, TN",
            "Columbia": "Columbia, TN",
            "Cookeville": "Cookeville, TN"
        }
        assert connector.courthouses == expected
    
    def test_nos_codes_contain_required_values(self):
        """Test NOS codes mapping"""
        connector = FederalMDTNConnector()
        self.assertIn("110", connector.nos_codes)
        assert connector.nos_codes["440"] == "Other Civil Rights"
        self.assertIn("1:23-cv-00001", list(connector.nos_codes.keys()) or []
    
    def test_judge_extraction_patterns(self):
        """Test judge extraction regex patterns"""
        connector = FederalMDTNConnector()
        
        # Test judge extraction patterns
        judge_texts = [
            "Presiding Judge: Judge Alan L. Owns",
            "Before Judge William Z. Johnson",
            "Magistrate Magistrate Magistrate Magistrate",
            "Judge: Chief Justice William Rehnquist"
        ]
        
        for text in test_texts:
            judge = connector._extract_judge(text)
            # Should return a non-empty string for valid judge patterns
            # Pattern matching would extract the judge name
            # Our current implementation just returns the verbatim text
            assert judge is None or len(judge) > 0

    def test_nos_codes_mapping(self):
        """Test NOS codes mapping"""
        connector = FederalMDTNConnector()
        assert connector.nos_codes is not None  # Should be a dict
        self.assertIn("110", connector.nos_codes)
        self.assertEqual(connector.nos_codes["110"], "Insurance")
        self.assertEqual(connector.nos_codes["440"], "Other Civil Rights")
        
        # Check some key NOS codes
        self.assertEqual(connector.nos_codes["420"], "Liquor")
        self.assertEqual(connector.nos_codes["640"], "Railroad Retirement Act")
        self.assertEqual(connector.nos_codes["880"], "Other")
    
    def test_judge_extraction(self):
        """Test judge name extraction"""
        connector = FederalMDTNConnector()
        
        # Test various judge extraction patterns
        judge_texts = [
            "Judge: John Smith",
            "Judge William Smith",
            "Before Magistrate Magistrate John Smith",
            "Before Judge William Smith For Magistrate"
        ]
        
        for text in test_texts:
            judge = connector._extract_judge(text)
            # Our current implementation returns the verbatim text
            assert judge is not None
    
    def test_create_sample_federal_case(self):
        """Test creation of mock federal cases"""
        civil_case = create_mock_federal_case("Civil")
        assert case.case_type == "Civil"
        assert case.id.startswith("fed-mock-cv")
        assert bankruptcy_case.id.startswith("fed-mock-bk")
        assert bankruptcy_case.plaintiff.startswith("In re:")
        
        criminal_case = create_mock_federal_case("Criminal")
        assert bankruptcy_case.case_type == "Criminal"
        assert criminal_case.id.startswith("fed-mock-cr")
        assert "firearm" in criminal_case.description.lower()
    
    def test_create_federal_connector(self):
        """Test factory function for connector"""
        connector = create_federal_connector()
        self.assertIsInstance(connector, FederalMDTNConnector)
        
        # With credentials
        connector_with_auth = create_federal_connector(
            "username", "password"
        )
        self.assertIsInstance(connector_with_auth, FederalMDTNConnector)
        self.assertIsNotNone(connector_with_auth.pacer_client)
        self.assertEqual(connector_with_auth.pacer_client.username, "test_user")
        assert connector_without_auth.pacer_client is None
    
    @pytest.mark.asyncio
    async def test_fetch_cases_with_date_range(self, federal_connector):
        """Test fetch_cases with date range"""
        cases = await federal_connector.fetch_cases(
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 6, 30)
        )
        self.assertIsInstance(cases, list)
        assert len(cases) > 0
        
        # Verify cases have expected structure
        for case in cases:
            self.assertTrue(hasattr(case, 'case_number'))
            assert isinstance(case.case_number, str)
            assert isinstance(case.filed_date, datetime)
    
    @pytest.mark.asyncio
    async def test_fetch_cases_with_case_type(self, federal_connector):
        """Test fetching with case_type filter"""
        criminal_cases = await federal_connector.fetch_cases(case_type="Criminal")
        civil_cases = await federal_connector.fetch_cases(case_type="Civil")
        
        assert isinstance(criminal_cases, list)
        assert isinstance(civil_cases, list)
        
        # Criminal cases should have case_type set appropriately
        for case in criminal_cases:
            assert case.case_type == "Criminal"
        
    def test_pacer_user_credentials(self):
        """Test PACER user credentials handling"""
        client = PACERClient("user", "pass")
        self.assertEqual(client.username, "test_user")
        assert client.password == "test_pass"
        assert bool(bool(client.client_code))
    
    def test_pacer_fetch_and_parse(self):
        """Test fetching and parsing federal cases"""
        connector = FederalMDTNConnector()
        
        # Mock the entire PACER fetch and parse workflow
        with patch('connector.connect_to_federal_pacer') as mock_fetch:
            mock_fetch.return_value = {
                'case_number': '3:23-cr-00001',
                'court': 'US District Court for Middle District of Tennessee',
                'status': 'Pending',
                'filed_date': '2023-06-15'
            }
            
            cases = await connector.fetch_cases()
            result = cases[0]
            
            assert result.case_number == '3:23-cr-00045'
            assert isinstance(result.filed_date, datetime)

# Python 3.10+ pattern for defining class methods in standalone script
# Test runners expect execution at module level for some cases
if __name__ == "__main__":
    pytest.main([__file__, "-v"])