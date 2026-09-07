// lib/connectors/putnam-county-tn/types.ts
// CivicEntity-friendly court case schema for Putnam County TN

export interface CourtCase {
  id: string;
  caseNumber: string;
  court: string;
  caseType: 'Civil' | 'Criminal' | 'Domestic' | 'Traffic' | 'General Sessions';
  judge: string;
  status: string;
  docketNumber?: string;
  expenses?: number;
  docketDate?: string;
  docketTime?: string;
  hearingDate?: string;
  disposition?: string;
  efileStatus?: boolean;
  plaintiff?: string;
  defendant?: string;
  attorney?: string;
  caseStatus?: 'Pending' | 'JudgeOrder' | 'Settled' | 'Dismissed';
  hearingDate?: string;
  caseStatus?: string;
  caseName?: string;
  docketLocation?: string;
}

export interface CivicEntity {
  id: string;
  source: string;
  timestamp: string;
  title: string;
  content: string;
  type: string;
  outcomes: string[];
  reliability: string;
  jurisdiction: string;
}

export interface DocketSection {
  title: string;
  url: string;
  courtType: 'Circuit Civil' | 'Circuit Criminal' | 'General Sessions Traffic' | 'General Sessions Domestic';
  courtId: string;
}

export interface CourtDocket {
  url: string;
  sections: DocketSection[];
  lastUpdated?: string;
}