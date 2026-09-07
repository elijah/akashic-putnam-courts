# src/connectors/federal-md-tn/connector.py
"""
Federal Court Connector (Multi-District Tennessee)
Handles PACER and federal court data with compliance validation
"""
import os
import re
import json
import logging
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from abc import ABC, abstractmethod

import requests
from pydantic import BaseModel, validator, Field

logger = logging.getLogger(__name__)

# === Federal Court Specific Models ===

class FederalCaseModel(BaseModel):
    """Pydantic model for federal court case data"""
    id: str
    case_number: str
    court: str  # e.g., "US District Court for Middle District of Tennessee"
    division: Optional[str] = None  # e.g., "Nashville", "Columbia"
    case_type: str = Field(..., pattern="^(Civil|Criminal|Bankruptcy|Appeal)$")
    nature_of_suit: Optional[str] = None  # Civil case codes
    offense: Optional[str] = None  # Criminal case codes
    status: str = Field(..., pattern="^(Pending|Terminated|Closed|Appealed)$")
    filed_date: datetime
    terminated_date: Optional[datetime] = None
    judge: Optional[str] = None
    magistrate_judge: Optional[str] = None
    plaintiff: Optional[str] = None
    defendant: Optional[str] = None
    docket_number: Optional[str] = None
    pacer_doc_id: Optional[str] = None
    cm_ecf_path: Optional[str] = None
    cm_ecf_doc_id: Optional[str] = None
    filing_fee: Optional[float] = None
    has_pdf: bool = False
    num_documents: int = 0

    @validator('filed_date', 'terminated_date', pre=True)
    def parse_dates(cls, v):
        if isinstance(v, str):
            # Handle various date formats from PACER
            for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
                try:
                    return datetime.strptime(v, fmt)
                except ValueError:
                    continue
            # Try ISO format
            try:
                return datetime.fromisoformat(v.replace('Z', '+00:00'))
            except ValueError:
                pass
        return v

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}

class FederalCivicEntityModel(BaseModel):
    """CivicEntity-compatible output for federal cases"""
    id: str
    source: str
    timestamp: datetime
    title: str
    content: str
    type: str = "federal_case"
    outcomes: List[str]
    reliability: str = Field(..., pattern="^(high|medium|low)$")
    jurisdiction: str = "Federal Court - Middle District of Tennessee"
    case_type: str
    federal_district: str = "MDTN"

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}

# === Exceptions ===

class FederalCourtError(Exception):
    """Base exception for federal court connector errors"""
    pass

class PACERError(FederalCourtError):
    """PACER specific errors"""
    pass

class FederalComplianceError(FederalCourtError):
    """Federal compliance errors (PACER fees, privacy, etc.)"""
    pass

# === Abstract Base Classes ===

class BaseFederalCourtConnector(ABC):
    """Abstract base class for federal court connectors"""
    
    @abstractmethod
    async def fetch_cases(self, 
                         start_date: Optional[datetime] = None,
                         end_date: Optional[datetime] = None,
                         case_type: Optional[str] = None) -> List[FederalCaseModel]:
        """Fetch federal court cases"""
        pass
    
    @abstractmethod
    def map_to_civic_entity(self, case: FederalCaseModel) -> FederalCivicEntityModel:
        """Map federal case to CivicEntity format"""
        pass
    
    @abstractmethod
    def validate_compliance(self, case: FederalCaseModel) -> bool:
        """Validate federal compliance (PACER, privacy, etc.)"""
        pass

# === PACER Configuration ===

PACER_CONFIG = {
    "base_url": "https://pacer.uscourts.gov",
    "api_endpoint": "/case-information/",
    "login_required": True,
    "fee_per_page": 0.10,  # $0.10 per page (as of 2024)
    "max_free_pages": 150,  # Quarterly free allowance
    "privacy_exemptions": [
        "Social Security Numbers",
        "Tax Identification Numbers", 
        "Birth Dates",
        "Minors' Names",
        "Financial Account Numbers",
        "Home Addresses",
        "Name of minor child"
    ]
}

# === PACER Client ===

class PACERClient:
    """PACER API client with rate limiting and cost tracking"""
    
    def __init__(self, username: str, password: str, 
                 client_code: str = ""):
        self.username = username
        self.password = password
        self.client_code = client_code
        self.session = requests.Session()
        self.quarterly_usage = 0  # Track pages used this quarter
        self.last_reset = datetime.now().replace(day=1)
        self._login()
    
    def _reset_quarterly_usage(self):
        """Reset usage counter at start of new quarter"""
        now = datetime.now()
        if (now.month - self.last_reset.month) >= 3 or \
           (now.year - self.last_reset.year) > 0:
            self.quarterly_usage = 0
            self.last_reset = now.replace(day=1, month=((now.month-1)//3)*3+1)
    
    def _login(self):
        """Authenticate with PACER"""
        # In production, this would use actual PACER authentication
        # For now, we'll simulate
        self.session.auth = (self.username, self.password)
        logger.info("PACER client initialized")
    
    def _make_request(self, endpoint: str, params: Dict = None) -> Dict:
        """Make authenticated request to PACER"""
        self._reset_quarterly_usage()
        
        url = f"{PACER_CONFIG['base_url']}{endpoint}"
        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            # Estimate pages used (simplified)
            content_length = len(response.content)
            estimated_pages = max(1, content_length // 1000)  # Rough estimate
            self.quarterly_usage += estimated_pages
            
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"PACER request failed: {e}")
            raise PACERError(f"PACER API error: {e}")
    
    def get_usage_report(self) -> Dict[str, Any]:
        """Get current usage statistics"""
        self._reset_quarterly_usage()
        return {
            "pages_used": self.quarterly_usage,
            "free_allowance": PACER_CONFIG["max_free_pages"],
            "remaining": max(0, PACER_CONFIG["max_free_pages"] - self.quarterly_usage),
            "estimated_cost": max(0, (self.quarterly_usage - PACER_CONFIG["max_free_pages"]) * PACER_CONFIG["fee_per_page"]),
            "quarter_start": self.last_reset.isoformat()
        }

# === Federal Court Implementation ===

class FederalMDTNConnector(BaseFederalCourtConnector):
    """Federal Court - Middle District of Tennessee connector"""
    
    def __init__(self, pacer_username: str = None, pacer_password: str = None):
        self.pacer_client = None
        if pacer_username and pacer_password:
            self.pacer_client = PACERClient(pacer_username, pacer_password)
        
        # MDTN specific courthouses
        self.courthouses = {
            "Nashville": "Nashville, TN",
            "Columbia": "Columbia, TN", 
            "Cookeville": "Cookeville, TN"
        }
        
        # Nature of Suit codes (Civil cases)
        self.nos_codes = {
            "110": "Insurance",
            "120": "Marine Contract",
            "130": "Miller Act",
            "140": "Negotiable Instrument",
            "150": "Recovery of Overpayment & Enforcement of Judgment",
            "151": "Medicare Act",
            "152": "Recovery of Defaulted Student Loans",
            "153": "Recovery of Overpayment of Veteran's Benefits",
            "160": "Stockholders' Suits",
            "190": "Other Contract",
            "195": "Contract Product Liability",
            "196": "Social Security",
            "210": "Land Condemnation",
            "220": "Foreclosure",
            "230": "Rent, Lease, & Ejectment",
            "240": "Torts to Land",
            "245": "Tort Product Liability",
            "290": "Other Real Property",
            "310": "Airplane",
            "315": "Airplane Product Liability",
            "320": "Assault, Libel, & Slander",
            "330": "Federal Employers' Liability",
            "340": "Marine",
            "345": "Marine Product Liability",
            "350": "Motor Vehicle",
            "355": "Motor Vehicle Product Liability",
            "360": "Other Personal Injury",
            "362": "Medical Malpractice",
            "365": "Personal Injury Product Liability",
            "368": "Asbestos Personal Injury Product Liability",
            "370": "Other Fraud",
            "371": "Truth in Lending",
            "380": "Other Personal Property Damage",
            "385": "Property Damage Product Liability",
            "390": "Other Personal Property Damage",
            "410": "Antitrust",
            "420": "Liquor",
            "430": "Copyright",
            "435": "Patent",
            "440": "Other Civil Rights",
            "441": "Voting",
            "442": "Employment",
            "443": "Housing/Accommodations",
            "445": "Americans with Disabilities - Employment",
            "446": "Americans with Disabilities - Other",
            "450": "Interstate Commerce",
            "460": "Deportation",
            "462": "Naturalization",
            "463": "Habeas Corpus - Alien Detainee",
            "465": "Other Immigration Actions",
            "470": "Racketeer Influenced and Corrupt Organizations",
            "480": "Consumer Credit",
            "490": "Cable/Satellite TV",
            "491": "Vessel Pollution",
            "495": "Atomic Energy",
            "510": "Bankruptcy Appeals",
            "520": "Patent - Abbreviated New Drug Application",
            "525": "Patent - Paragraph IV",
            "530": "General",
            "535": "Death Penalty - Other",
            "540": "Mandamus & Other",
            "550": "Prisoner - Civil Rights",
            "555": "Prisoner - Prison Condition",
            "560": "Civil Detainee - Conditions of Confinement",
            "570": "Real Property",
            "580": "Other Deportation",
            "610": "Agriculture",
            "620": "Bankruptcy Rules & Procedures",
            "630": "Liquor Laws",
            "640": "Railroad Retirement",
            "650": "Oversee & Lien",
            "660": "Other Civil Rights",
            "690": "Other",
            "710": "Fair Labor Standards Act",
            "720": "Labor/Management Relations",
            "730": "Labor/Management Reporting & Disclosure Act",
            "740": "Railway Labor Act",
            "750": "Family and Medical Leave Act",
            "760": "Other Labor Litigation",
            "770": "Bankruptcy",
            "790": "Other Labor Litigation",
            "810": "Selective Service",
            "820": "Copyrights",
            "830": "Patent",
            "840": "Trademark",
            "850": "Securities/Commodities/Exchange",
            "860": "Social Security",
            "861": "HIA (1395ff)",
            "862": "Black Lung (923)",
            "863": "DIWC/DIWW (405(g))",
            "864": "SSID Title XVI",
            "865": "RSI (title IX)",
            "870": "Taxes (U.S. Plaintiff)",
            "871": "IRS - Third Party 26 USC 7609",
            "872": "Taxes (U.S. Defendant) 872",
            "890": "Other Statutory Actions",
            "891": "Agricultural Acts",
            "893": "Environmental Matters",
            "895": "Freedom of Information Act",
            "896": "Arbitration",
            "899": "Administrative Procedure Act",
            "910": "Equal Pay",
            "920": "Civil Rights",
            "930": "Environmental Matters",
            "940": "Other",
            "950": "DDT/SASA"
        }
        
        # Offense codes (Criminal cases)
        self.offense_codes = {
            "1": "A",
            "2": "B", 
            "3": "C",
            "4": "D",
            "5": "E",
            "6": "F",
            "7": "G",
            "8": "H",
            "9": "I",
            "10": "J",
            "11": "K",
            "12": "L",
            "13": "M",
            "14": "N",
            "15": "O",
            "16": "P",
            "17": "Q",
            "18": "R",
            "19": "S",
            "20": "T",
            "21": "U",
            "22": "V",
            "23": "W",
            "24": "X",
            "25": "Y",
            "26": "Z"
        }
    
    async def fetch_cases(self, 
                         start_date: Optional[datetime] = None,
                         end_date: Optional[datetime] = None,
                         case_type: Optional[str] = None) -> List[FederalCaseModel]:
        """Fetch federal court cases from PACER or public sources"""
        if not self.pacer_client:
            logger.warning("PACER credentials not provided, using mock data")
            return await self._fetch_mock_data()
        
        try:
            # Set default date range if not provided
            if not end_date:
                end_date = datetime.now()
            if not start_date:
                start_date = end_date - timedelta(days=30)  # Last 30 days
            
            # Format dates for PACER
            start_str = start_date.strftime("%m/%d/%Y")
            end_str = end_date.strftime("%m/%d/%Y")
            
            # Query PACER for recent cases
            params = {
                "date_filed_after": start_str,
                "date_filed_before": end_str,
                "case_type": case_type or "",
                "format": "json"
            }
            
            response = self.pacer_client._make_request(
                "/case-information/case-search/", 
                params=params
            )
            
            cases = []
            for case_data in response.get("results", []):
                try:
                    federal_case = self._parse_pacer_case(case_data)
                    cases.append(federal_case)
                except Exception as e:
                    logger.error(f"Failed to parse PACER case {case_data.get('case_number')}: {e}")
                    continue
            
            return cases
            
        except Exception as e:
            logger.error(f"Failed to fetch federal cases: {e}")
            # Fallback to mock data for development
            return await self._fetch_mock_data()
    
    async def _fetch_mock_data(self) -> List[FederalCaseModel]:
        """Generate mock federal court data for testing"""
        mock_cases = [
            FederalCaseModel(
                id="fed-case-001",
                case_number="3:23-cr-00045",
                court="US District Court for Middle District of Tennessee",
                division="Nashville",
                case_type="Criminal",
                nature_of_suit=None,
                offense="18 USC § 922(g)(1) - Felon in possession of firearm",
                status="Pending",
                filed_date=datetime(2023, 6, 15),
                terminated_date=None,
                judge="William L. Campbell, Jr.",
                magistrate_judge=None,
                plaintiff="United States of America",
                defendant="John Doe",
                docket_number="3:23-cr-00045-WLC",
                pacer_doc_id="12345678",
                cm_ecf_path="/cfd/mdtn",
                cm_ecf_doc_id="87654321",
                filing_fee=0.0,
                has_pdf=True,
                num_documents=12
            ),
            FederalCaseModel(
                id="fed-case-002",
                case_number="3:22-cv-00567",
                court="US District Court for Middle District of Tennessee", 
                division="Nashville",
                case_type="Civil",
                nature_of_suit="440 - Other Civil Rights",
                offense=None,
                status="Terminated",
                filed_date=datetime(2022, 10, 5),
                terminated_date=datetime(2023, 3, 20),
                judge="Aleta Arthur Trauger",
                magistrate_judge=None,
                plaintiff="Jane Smith",
                defendant="Metropolitan Government of Nashville",
                docket_number="3:22-cv-00567-AAT",
                pacer_doc_id="23456789",
                cm_ecf_path="/cfd/mdtn",
                cm_ecf_doc_id="98765432",
                filing_fee=400.0,
                has_pdf=True,
                num_documents=45
            ),
            FederalCaseModel(
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
                judge=None,  # Bankruptcy cases have trustees
                magistrate_judge=None,
                plaintiff="In re: William Johnson",
                defendant=None,
                docket_number="3:21-bk-01234",
                pacer_doc_id="34567890",
                cm_ecf_path="/cfd/mdtn-bk",
                cm_ecf_doc_id="09876543",
                filing_fee=335.0,
                has_pdf=True,
                num_documents=28
            )
        ]
        return mock_cases
    
    def _parse_pacer_case(self, pacer_data: Dict[str, Any]) -> FederalCaseModel:
        """Parse PACER API response into FederalCaseModel"""
        # Extract basic information
        case_number = pacer_data.get("case_number", "")
        court_name = pacer_data.get("court_name", "US District Court for Middle District of Tennessee")
        
        # Determine division from court name or filing location
        division = "Nashville"  # Default
        if "Columbia" in pacer_data.get("filing_location", ""):
            division = "Columbia"
        elif "Cookeville" in pacer_data.get("filing_location", ""):
            division = "Cookeville"
        
        # Parse dates
        filed_date = None
        if pacer_data.get("date_filed"):
            try:
                filed_date = datetime.strptime(pacer_data["date_filed"], "%m/%d/%Y")
            except ValueError:
                pass
        
        terminated_date = None
        if pacer_data.get("date_terminated"):
            try:
                terminated_date = datetime.strptime(pacer_data["date_terminated"], "%m/%d/%Y")
            except ValueError:
                pass
        
        # Determine case type
        case_type = "Civil"
        if pacer_data.get("case_type") == "CR":
            case_type = "Criminal"
        elif pacer_data.get("case_type") == "BK":
            case_type = "Bankruptcy"
        
        # Get nature of suit or offense
        nature_of_suit = pacer_data.get("nature_of_suit_code")
        offense = pacer_data.get("statute")
        
        # Get judge information
        judge = pacer_data.get("assigned_to")
        magistrate_judge = pacer_data.get("referred_to")
        
        # Get parties
        plaintiff = pacer_data.get("plaintiff")
        defendant = pacer_data.get("defendant")
        
        # Build federal case
        return FederalCaseModel(
            id=f"fed-{hashlib.md5(case_number.encode()).hexdigest()[:8]}",
            case_number=case_number,
            court=court_name,
            division=division,
            case_type=case_type,
            nature_of_suit=nature_of_suit,
            offense=offense,
            status=pacer_data.get("status", "Pending"),
            filed_date=filed_date or datetime.now(),
            terminated_date=terminated_date,
            judge=judge,
            magistrate_judge=magistrate_judge,
            plaintiff=plaintiff,
            defendant=defendant,
            docket_number=pacer_data.get("docket_number"),
            pacer_doc_id=pacer_data.get("pacer_doc_id"),
            cm_ecf_path=pacer_data.get("cm_ecf_path"),
            cm_ecf_doc_id=pacer_data.get("cm_ecf_doc_id"),
            filing_fee=float(pacer_data.get("filing_fee", 0.0)),
            has_pdf=bool(pacer_data.get("has_pdf")),
            num_documents=int(pacer_data.get("num_documents", 0))
        )
    
    def map_to_civic_entity(self, federal_case: FederalCaseModel) -> FederalCivicEntityModel:
        """Map FederalCaseModel to FederalCivicEntityModel"""
        # Build title
        title_parts = []
        if federal_case.case_type:
            title_parts.append(f"[{federal_case.case_type}]")
        title_parts.append(federal_case.case_number)
        if federal_case.status:
            title_parts.append(f"- {federal_case.status}")
        
        title = " ".join(title_parts)
        
        # Build content
        content_lines = [
            f"Federal Case #{federal_case.case_number}",
            f"Court: {federal_case.court}",
        ]
        
        if federal_case.division:
            content_lines.append(f"Division: {federal_case.division}")
            
        if federal_case.judge:
            content_lines.append(f"Judge: {federal_case.judge}")
        if federal_case.magistrate_judge:
            content_lines.append(f"Magistrate Judge: {federal_case.magistrate_judge}")
            
        content_lines.append(f"Filed: {federal_case.filed_date.strftime('%Y-%m-%d')}")
        if federal_case.terminated_date:
            content_lines.append(f"Terminated: {federal_case.terminated_date.strftime('%Y-%m-%d')}")
            
        if federal_case.nature_of_suit:
            nos_desc = self.nos_codes.get(federal_case.nature_of_suit, f"Code {federal_case.nature_of_suit}")
            content_lines.append(f"Nature of Suit: {nos_desc} ({federal_case.nature_of_suit})")
            
        if federal_case.offense:
            content_lines.append(f"Offense: {federal_case.offense}")
            
        if federal_case.plaintiff:
            content_lines.append(f"Plaintiff: {federal_case.plaintiff}")
        if federal_case.defendant:
            content_lines.append(f"Defendant: {federal_case.defendant}")
            
        content_lines.append(f"Status: {federal_case.status}")
        
        if federal_case.docket_number:
            content_lines.append(f"Docket Number: {federal_case.docket_number}")
            
        content_lines.append(f"ECF Available: {'Yes' if federal_case.has_pdf else 'No'}")
        if federal_case.num_documents > 0:
            content_lines.append(f"Number of Documents: {federal_case.num_documents}")
            
        if federal_case.filing_fee > 0:
            content_lines.append(f"Filing Fee: ${federal_case.filing_fee:.2f}")
        
        content = "\n".join(content_lines)
        
        # Determine outcomes
        outcomes = [federal_case.status]
        if federal_case.terminated_date:
            outcomes.append("Terminated")
        if federal_case.disposition and federal_case.disposition != federal_case.status:
            outcomes.append(federal_case.disposition)
        
        # Determine reliability based on PACER availability and completeness
        reliability = "high"
        missing_fields = []
        if not federal_case.judge:
            missing_fields.append("judge")
        if not federal_case.filed_date:
            missing_fields.append("filed_date")
        if federal_case.num_documents == 0:
            missing_fields.append("documents")
        if not federal_case.has_pdf:
            missing_fields.append("pdf")
            
        if len(missing_fields) > 2:
            reliability = "low"
        elif len(missing_fields) > 0:
            reliability = "medium"
            
        return FederalCivicEntityModel(
            id=federal_case.id,
            source="PACER - Middle District of Tennessee",
            timestamp=federal_case.filed_date,
            title=title,
            content=content,
            type="federal_case",
            outcomes=list(set(outcomes)),  # Remove duplicates
            reliability=reliability,
            jurisdiction="Federal Court - Middle District of Tennessee",
            case_type=federal_case.case_type,
            federal_district="MDTN"
        )
    
    def validate_compliance(self, federal_case: FederalCaseModel) -> bool:
        """Validate federal compliance (PACER rules, privacy, etc.)"""
        # Check 1: Required fields
        required_fields = ["id", "case_number", "court", "case_type", "status", "filed_date"]
        for field in required_fields:
            if not getattr(federal_case, field, None):
                logger.debug(f"Missing required field: {field}")
                return False
        
        # Check 2: PII detection in plaintiff/defendant names
        pii_patterns = [
            r'\b\d{3}-\d{2}-\d{4}\b',  # SSN
            r'\b\d{9}\b',  # EIN/ITIN (9 digits)
            r'\b\d{3}-\d{3}-\d{4}\b',  # Phone (could be PII in some contexts)
            r'\b\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\b',  # Credit card
        ]
        
        text_to_check = f"{federal_case.plaintiff or ''} {federal_case.defendant or ''} {federal_case.offense or ''}"
        for pattern in pii_patterns:
            if re.search(pattern, text_to_check):
                logger.debug(f"PII detected in federal case {federal_case.case_number}: {pattern}")
                return False
        
        # Check 3: Date validity
        if federal_case.filed_date > datetime.now() + timedelta(days=365):
            logger.debug(f"Future filing date for {federal_case.case_number}")
            return False
            
        if federal_case.terminated_date and federal_case.terminated_date < federal_case.filed_date:
            logger.debug(f"Terminated before filed for {federal_case.case_number}")
            return False
        
        # Check 4: PACER compliance (if using PACER)
        if self.pacer_client:
            # Check if we're exceeding free allowance (warning only)
            usage = self.pacer_client.get_usage_report()
            if usage["remaining"] < 0:
                logger.warning(f"PACER usage exceeded free allowance: {usage['estimated_cost']:.2f}")
                # Don't fail validation, just warn - user may have paid for additional pages
        
        # Check 5: Case number format validation
        # Federal case numbers typically follow patterns like:
        # 1:23-cv-00123, 2:22-cr-00456, 3:21-bk-00789
        case_number_pattern = r'^\d+:\d{2}-(cv|cr|bk|ap)-\d{6}$'
        if not re.match(case_number_pattern, federal_case.case_number, re.IGNORECASE):
            # Allow for variations
            alt_pattern = r'^\d+:\d{2}-[a-z]{2}-\d+$'
            if not re.match(alt_pattern, federal_case.case_number, re.IGNORECASE):
                logger.debug(f"Unusual case number format: {federal_case.case_number}")
                # Don't fail validation, just log - some courts use different formats
        
        return True

# === Utility Functions ===

def create_mock_federal_case(case_type: str = "Civil") -> FederalCaseModel:
    """Create a mock federal case for testing"""
    base_time = datetime(2023, 6, 15)
    
    if case_type == "Criminal":
        return FederalCaseModel(
            id="fed-mock-cr-001",
            case_number="3:23-cr-00123",
            court="US District Court for Middle District of Tennessee",
            division="Nashville",
            case_type="Criminal",
            offense="21 USC § 841(a)(1) - Distribution of controlled substance",
            status="Pending",
            filed_date=base_time,
            plaintiff="United States of America",
            defendant="Juan Martinez",
            docket_number="3:23-cr-00123",
            has_pdf=True,
            num_documents=8
        )
    elif case_type == "Bankruptcy":
        return FederalCaseModel(
            id="fed-mock-bk-001",
            case_number="3:22-bk-00456",
            court="US Bankruptcy Court for Middle District of Tennessee",
            division="Cookeville",
            case_type="Bankruptcy",
            status="Closed",
            filed_date=datetime(2022, 11, 30),
            terminated_date=datetime(2023, 2, 10),
            plaintiff="In re: Sarah Thompson",
            docket_number="3:22-bk-00456",
            has_pdf=True,
            num_documents=15,
            filing_fee=335.0
        )
    else:  # Civil
        return FederalCaseModel(
            id="fed-mock-cv-001",
            case_number="3:23-cv-00456",
            court="US District Court for Middle District of Tennessee",
            division="Nashville",
            case_type="Civil",
            nature_of_suit="440",
            status="Pending",
            filed_date=datetime(2023, 5, 20),
            plaintiff="Jessica Williams",
            defendant="Acme Corporation",
            docket_number="3:23-cv-00456",
            has_pdf=True,
            num_documents=22,
            filing_fee=400.0
        )

def validate_federal_case_legacy(case_data: Dict[str, Any]) -> bool:
    """Legacy validation function for backward compatibility"""
    required = ["case_number", "court", "case_type", "status", "filed_date"]
    return all(field in case_data and case_data[field] for field in required)

# === Factory Functions ===

def create_federal_connector(pacer_username: str = None, 
                           pacer_password: str = None) -> FederalMDTNConnector:
    """Factory function to create federal court connector"""
    return FederalMDTNConnector(pacer_username, pacer_password)

# === Health Check ===

def health_check() -> Dict[str, Any]:
    """Return health status of federal connector"""
    try:
        # Test basic functionality
        conn = FederalMDTNConnector()
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "components": {
                "connector": "initialized",
                "pacer_client": "available" if pacer_username and pacer_password else "not_configured"
            }
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }