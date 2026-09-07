# src/connectors/putnam-county-tn-python/connector.py
"""
Putnam County TN Court Connector - Python Implementation
Supports Django integration, PDF parsing, PII detection, and TN Open Records Act compliance
"""
import os
import re
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from abc import ABC, abstractmethod

import requests
import pdfplumber
from pydantic import BaseModel, validator, Field

logger = logging.getLogger(__name__)

# === Data Models ===

class CourtCaseModel(BaseModel):
    """Pydantic model for court case data validation"""
    id: str
    case_number: str
    court: str = "Putnam County Circuit Court"
    case_type: str = Field(..., pattern="^(Civil|Criminal|Domestic|Traffic|General Sessions)$")
    status: str = Field(..., pattern="^(Pending|Scheduled|Settled|Dismissed|JudgeOrder)$")
    docket_date: datetime
    disposition: str
    docket_number: str
    expenses: float = 0.0
    efile_status: bool = True
    plaintiff: Optional[str] = None
    defendant: Optional[str] = None
    attorney: Optional[str] = None
    judge: Optional[str] = None
    docket_time: Optional[str] = None
    docket_location: Optional[str] = None
    hearing_date: Optional[datetime] = None
    case_status: Optional[str] = None

    @validator('docket_date', 'hearing_date', pre=True)
    def parse_dates(cls, v):
        if isinstance(v, str):
            return datetime.fromisoformat(v.replace('Z', '+00:00'))
        return v

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}

class CivicEntityModel(BaseModel):
    """CivicEntity-compatible output model"""
    id: str
    source: str
    timestamp: datetime
    title: str
    content: str
    type: str = "court_case"
    outcomes: List[str]
    reliability: str = Field(..., pattern="^(high|medium|low)$")
    jurisdiction: str = "Putnam County, Tennessee"

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}

class DigitalAssetModel(BaseModel):
    """Digital asset for document storage"""
    source_url: str
    file_content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    model_version: str = "1.0.0"
    layer_metadata: Dict[str, Any] = Field(default_factory=dict)

class IdentityModel(BaseModel):
    """Identity layer for entity tracking"""
    entity_id: str
    version: int
    ownership: List[str] = Field(default_factory=list)
    layer_metadata: Dict[str, Any] = Field(default_factory=dict)

# === Exceptions ===

class CourtConnectorError(Exception):
    """Base exception for court connector errors"""
    pass

class PDFParseError(CourtConnectorError):
    """PDF parsing specific errors"""
    pass

class ComplianceError(CourtConnectorError):
    """TN Open Records Act compliance errors"""
    pass

# === Abstract Base Classes ===

class BaseCourtConnector(ABC):
    """Abstract base class for court connectors"""
    
    @abstractmethod
    async def fetch_dockets(self) -> List[CourtCaseModel]:
        """Fetch and parse court docket data"""
        pass
    
    @abstractmethod
    def map_to_civic_entity(self, case: CourtCaseModel) -> CivicEntityModel:
        """Map court case to CivicEntity format"""
        pass
    
    @abstractmethod
    def validate_compliance(self, case: CourtCaseModel) -> bool:
        """Validate TN Open Records Act compliance"""
        pass

# === Putnam County TN Implementation ===

class PutnamCountyTNConnector(BaseCourtConnector):
    """Putnam County Circuit Court connector with full compliance"""
    
    DOCKET_SECTIONS = [
        {
            "title": "Circuit Civil Docket",
            "url": "https://putnamtncourtclerk.gov/wp-content/uploads/2026/07/CCivKnight071326.pdf",
            "court_type": "Civil"
        },
        {
            "title": "Circuit Criminal Docket", 
            "url": "https://putnamtncourtclerk.gov/wp-content/uploads/2026/07/CCriminal073026-1.pdf",
            "court_type": "Criminal"
        },
        {
            "title": "General Sessions Traffic Docket",
            "url": "https://putnamtncourtclerk.gov/wp-content/uploads/2026/08/GSTraffic080726.pdf",
            "court_type": "Traffic"
        },
        {
            "title": "General Sessions Civil Docket",
            "url": "https://putnamtncourtclerk.gov/wp-content/uploads/2026/07/GSCivil080426.pdf",
            "court_type": "Civil"
        },
        {
            "title": "General Sessions Criminal Docket",
            "url": "https://putnamtncourtclerk.gov/wp-content/uploads/2026/08/GSCriminal080526.pdf",
            "court_type": "Criminal"
        },
        {
            "title": "General Sessions Domestic Docket",
            "url": "https://putnamtncourtclerk.gov/wp-content/uploads/2026/07/GSDomestic07282026.pdf",
            "court_type": "Domestic"
        }
    ]
    
    def __init__(self, timeout: int = 30, max_retries: int = 3):
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Akashic Court Connector/1.0 (TN Open Records Act Request)"
        })
    
    async def fetch_dockets(self) -> List[CourtCaseModel]:
        """Fetch all docket sections and parse cases"""
        all_cases = []
        
        for section in self.DOCKET_SECTIONS:
            try:
                logger.info(f"Fetching {section['title']} from {section['url']}")
                cases = await self._fetch_and_parse_section(section)
                all_cases.extend(cases)
            except Exception as e:
                logger.error(f"Failed to fetch {section['title']}: {e}")
                continue
        
        return all_cases
    
    async def _fetch_and_parse_section(self, section: Dict[str, str]) -> List[CourtCaseModel]:
        """Fetch PDF and extract case data"""
        response = self.session.get(section["url"], timeout=self.timeout)
        response.raise_for_status()
        
        # Save PDF temporarily for parsing
        temp_path = f"/tmp/{section['court_type']}_docket.pdf"
        with open(temp_path, 'wb') as f:
            f.write(response.content)
        
        try:
            cases = self._parse_pdf(temp_path, section["court_type"])
            return cases
        finally:
            # Cleanup temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)
    
    def _parse_pdf(self, pdf_path: str, court_type: str) -> List[CourtCaseModel]:
        """Extract court case data from PDF using pdfplumber"""
        cases = []
        
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages):
                    text = page.extract_text()
                    if not text:
                        continue
                    
                    # Parse case data from text
                    page_cases = self._extract_cases_from_text(text, court_type)
                    cases.extend(page_cases)
                    
        except Exception as e:
            logger.error(f"PDF parsing error for {pdf_path}: {e}")
            raise PDFParseError(f"Failed to parse PDF: {e}")
        
        return cases
    
    def _extract_cases_from_text(self, text: str, court_type: str) -> List[CourtCaseModel]:
        """Extract individual cases from PDF text using regex patterns"""
        cases = []
        
        # Pattern for CASE FILED entries
        case_pattern = re.compile(
            r'CASE\s+FILED:\s*(\d{4}-\d{2}-\d{2})\s+'
            r'CASE\s*#:\s*(\S+)\s+'
            r'CASE\s+TYPE:\s*(\w+)\s+'
            r'STATEMENT_(.+?)(?=CASE\s+FILED:|$)',
            re.DOTALL | re.IGNORECASE
        )
        
        for match in case_pattern.finditer(text):
            try:
                docket_date_str, case_number, case_type, statement = match.groups()
                
                # Extract plaintiff/defendant from statement
                plaintiff, defendant = self._parse_parties(statement)
                
                # Create court case model
                case = CourtCaseModel(
                    id=f"{case_number}_{court_type}",
                    case_number=case_number.strip(),
                    court="Putnam County Circuit Court",
                    case_type=court_type,
                    status="Pending",  # Default, would be extracted from full data
                    docket_date=datetime.fromisoformat(docket_date_str.strip()),
                    disposition="Pending",
                    docket_number=case_number.strip(),
                    expenses=0.0,
                    efile_status=True,
                    plaintiff=plaintiff,
                    defendant=defendant,
                    judge=self._extract_judge(statement)
                )
                cases.append(case)
                
            except Exception as e:
                logger.warning(f"Failed to parse case from match: {e}")
                continue
        
        return cases
    
    def _parse_parties(self, statement: str) -> tuple:
        """Extract plaintiff and defendant from case statement"""
        # Common patterns: "Plaintiff v. Defendant", "State v. Defendant"
        v_pattern = re.search(r'(.+?)\s+v\.\s+(.+)', statement, re.IGNORECASE)
        if v_pattern:
            return v_pattern.group(1).strip(), v_pattern.group(2).strip()
        
        vs_pattern = re.search(r'(.+?)\s+vs\.\s+(.+)', statement, re.IGNORECASE)
        if vs_pattern:
            return vs_pattern.group(1).strip(), vs_pattern.group(2).strip()
        
        return "Unknown Plaintiff", "Unknown Defendant"
    
    def _extract_judge(self, text: str) -> Optional[str]:
        """Extract judge name from text"""
        judge_patterns = [
            r'Judge\s+([A-Z][a-z]+\s+[A-Z][a-z]+)',
            r'J\.\s+([A-Z][a-z]+\s+[A-Z][a-z]+)',
            r'(William\s+Ridley|Caroline\s+Knight)'
        ]
        
        for pattern in judge_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None
    
    def map_to_civic_entity(self, case: CourtCaseModel) -> CivicEntityModel:
        """Map court case to CivicEntity format"""
        return CivicEntityModel(
            id=case.id,
            source="Putnam County Circuit Court (TN)",
            timestamp=case.docket_date,
            title=f"[{case.case_type}] {case.case_number} - {case.status}",
            content=self._format_case_content(case),
            type="court_case",
            outcomes=[case.status, case.disposition].filter(bool),
            reliability="high" if case.efile_status else "medium",
            jurisdiction="Putnam County, Tennessee"
        )
    
    def _format_case_content(self, case: CourtCaseModel) -> str:
        """Format case content for CivicEntity"""
        parts = [
            f"{case.case_type} Case #{case.case_number}",
            f"Court: {case.court}",
            f"Judge: {case.judge or 'Not specified'}",
            f"Status: {case.status}",
            f"Disposition: {case.disposition}",
            f"Docket Number: {case.docket_number}",
            f"Docket Date: {case.docket_date.strftime('%Y-%m-%d')}",
            f"E-file Status: {'Electronic Filing' if case.efile_status else 'Paper Filing'}",
            f"Plaintiff: {case.plaintiff or 'N/A'}",
            f"Defendant: {case.defendant or 'N/A'}",
            f"Attorney: {case.attorney or 'N/A'}"
        ]
        return "\n".join(parts)
    
    def validate_compliance(self, case: CourtCaseModel) -> bool:
        """Validate TN Open Records Act compliance"""
        # Check for required fields
        required_fields = ['case_number', 'docket_date', 'court']
        if not all(getattr(case, field) for field in required_fields):
            return False
        
        # Check for PII that shouldn't be in public records
        pii_indicators = ['SSN', 'Social Security', 'driver license', 'DL#', 'medical']
        content_to_check = f"{case.plaintiff or ''} {case.defendant or ''} {case.content if hasattr(case, 'content') else ''}"
        
        for indicator in pii_indicators:
            if indicator.lower() in content_to_check.lower():
                logger.warning(f"Potential PII detected: {indicator}")
                return False
        
        return True

# === Django Integration Layer ===

class DjangoCourtCase(models.Model):
    """Django ORM model for court cases"""
    id = models.CharField(max_length=255, primary_key=True)
    case_number = models.CharField(max_length=100)
    court = models.CharField(max_length=255)
    case_type = models.CharField(max_length=50, choices=[
        ('Civil', 'Civil'), ('Criminal', 'Criminal'), 
        ('Domestic', 'Domestic'), ('Traffic', 'Traffic'),
        ('General Sessions', 'General Sessions')
    ])
    status = models.CharField(max_length=50)
    docket_date = models.DateTimeField()
    disposition = models.CharField(max_length=100)
    docket_number = models.CharField(max_length=100)
    expenses = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    efile_status = models.BooleanField(default=True)
    plaintiff = models.CharField(max_length=255, blank=True, null=True)
    defendant = models.CharField(max_length=255, blank=True, null=True)
    attorney = models.CharField(max_length=255, blank=True, null=True)
    judge = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'court_cases'
        indexes = [
            models.Index(fields=['case_number']),
            models.Index(fields=['docket_date']),
            models.Index(fields=['court', 'case_type']),
        ]

class DjangoDigitalAsset(models.Model):
    """Django ORM model for digital assets (PDFs, documents)"""
    id = models.AutoField(primary_key=True)
    source_url = models.URLField()
    file_content = models.TextField()
    model_version = models.CharField(max_length=50, default='1.0.0')
    layer_metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'digital_assets'

class DjangoIdentity(models.Model):
    """Django ORM model for identity layer"""
    entity_id = models.CharField(max_length=255)
    version = models.IntegerField(default=1)
    ownership = models.JSONField(default=list)
    layer_metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'identities'
        unique_together = ['entity_id', 'version']

# === Django Service Layer ===

class CourtConnectorService:
    """Django service layer for court connector operations"""
    
    def __init__(self):
        self.connector = PutnamCountyTNConnector()
    
    async def sync_court_cases(self) -> Dict[str, Any]:
        """Sync court cases from source to database"""
        results = {
            "fetched": 0,
            "created": 0,
            "updated": 0,
            "errors": []
        }
        
        try:
            cases = await self.connector.fetch_dockets()
            results["fetched"] = len(cases)
            
            for case in cases:
                try:
                    # Validate compliance before saving
                    if not self.connector.validate_compliance(case):
                        results["errors"].append(f"Compliance failed for case {case.case_number}")
                        continue
                    
                    # Map to Django model
                    django_case, created = DjangoCourtCase.objects.update_or_create(
                        id=case.id,
                        defaults={
                            'case_number': case.case_number,
                            'court': case.court,
                            'case_type': case.case_type,
                            'status': case.status,
                            'docket_date': case.docket_date,
                            'disposition': case.disposition,
                            'docket_number': case.docket_number,
                            'expenses': case.expenses,
                            'efile_status': case.efile_status,
                            'plaintiff': case.plaintiff,
                            'defendant': case.defendant,
                            'attorney': case.attorney,
                            'judge': case.judge,
                        }
                    )
                    
                    if created:
                        results["created"] += 1
                    else:
                        results["updated"] += 1
                        
                    # Create CivicEntity record
                    civic_entity = self.connector.map_to_civic_entity(case)
                    # Store civic entity if needed
                    
                except Exception as e:
                    results["errors"].append(f"Case {case.case_number}: {str(e)}")
                    logger.error(f"Error processing case {case.case_number}: {e}")
        
        except Exception as e:
            results["errors"].append(f"Sync failed: {str(e)}")
            logger.error(f"Sync failed: {e}")
        
        return results
    
    def get_cases_by_type(self, case_type: str) -> List[DjangoCourtCase]:
        """Get cases filtered by type"""
        return DjangoCourtCase.objects.filter(case_type=case_type)
    
    def get_cases_by_date_range(self, start: datetime, end: datetime) -> List[DjangoCourtCase]:
        """Get cases within date range"""
        return DjangoCourtCase.objects.filter(
            docket_date__gte=start,
            docket_date__lte=end
        )

# === API Views ===

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

class CourtCaseViewSet(viewsets.ReadOnlyModelViewSet):
    """REST API for court cases"""
    queryset = DjangoCourtCase.objects.all()
    serializer_class = CourtCaseSerializer
    filterset_fields = ['case_type', 'status', 'court']
    search_fields = ['case_number', 'plaintiff', 'defendant']
    ordering_fields = ['docket_date', 'created_at']
    
    @action(detail=False, methods=['post'])
    async def sync(self, request):
        """Trigger manual sync"""
        service = CourtConnectorService()
        results = await service.sync_court_cases()
        return Response(results)

class CourtCaseSerializer(serializers.ModelSerializer):
    """Serializer for court cases"""
    class Meta:
        model = DjangoCourtCase
        fields = '__all__'

# === Management Commands ===

class Command(BaseCommand):
    """Django management command for syncing court cases"""
    help = 'Sync court cases from Putnam County TN sources'
    
    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help='Force re-sync')
    
    def handle(self, *args, **options):
        service = CourtConnectorService()
        results = asyncio.run(service.sync_court_cases())
        
        self.stdout.write(
            self.style.SUCCESS(
                f"Sync completed: {results['created']} created, "
                f"{results['updated']} updated, {len(results['errors'])} errors"
            )
        )
        
        if results['errors']:
            for error in results['errors']:
                self.stdout.write(self.style.ERROR(f"  - {error}"))