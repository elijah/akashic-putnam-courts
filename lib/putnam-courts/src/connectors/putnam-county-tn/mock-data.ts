// lib/connectors/putnam-county-tn/mock-data.ts
// Mock data for testing Putnam County TN court connector
// Simulates data from Putnam County Circuit Court Clerk PDFs

export interface CourtCaseMock {
  caseNumber: string;
  caseType: 'Civil' | 'Criminal' | 'Domestic';
  plaintiff?: string;
  defendant?: string;
  status: 'Pending' | 'JudgeOrder' | 'Settled' | 'Dismissed';
  docketDate: string;
  disposition?: string;
  expenses?: number;
}

// Mock data for testing
export const mockCases: CourtCaseMock[] = [
  {
    caseNumber: '2023-CCIV-001',
    caseType: 'Civil',
    plaintiff: 'Jane Doe',
    defendant: 'City of Cookeville',
    status: 'Pending',
    docketDate: '2023-07-13',
    disposition: 'Pending'
  },
  {
    caseNumber: '2023-CCRM-002',
    caseType: 'Criminal',
    plaintiff: 'State of TN',
    defendant: 'David Smith',
    status: 'Scheduled',
    docketDate: '2023-07-30',
    disposition: 'Pending'
  },
  {
    caseNumber: '2023-GSD-003',
    caseType: 'Domestic',
    plaintiff: 'Mary Johnson',
    defendant: 'John Smith',
    status: 'Settled',
    docketDate: '2023-06-20',
    disposition: 'Settlement Reached'
  }
];

// Mock docket sections
export const mockDocketSections: DocketSection[] = [
  {
    title: 'Circuit Civil Docket',
    url: 'https://putnamtncourtclerk.gov/wp-content/uploads/2026/07/CCivKnight071326.pdf',
    courtType: 'Circuit Civil'
  },
  {
    title: 'General Sessions Traffic Docket',
    url: 'https://putnamtncourtclerk.gov/wp-content/uploads/2026/08/GSTraffic080726.pdf',
    courtType: 'General Sessions Traffic'
  }
];