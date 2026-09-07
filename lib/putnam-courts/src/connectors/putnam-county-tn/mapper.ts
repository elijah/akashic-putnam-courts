// lib/connectors/putnam-county-tn/mapper.ts
// Maps court data to CivicEntity format
import { CourtCase, CivicEntity } from './types';

/**
 * Maps a CourtCase to a CivicEntity
 * @param courtCase The court case data to map
 * @returns Mapped CivicEntity
 */
export function mapCourtCaseToCivicEntity(courtCase: CourtCase): CivicEntity {
  return {
    id: courtCase.id || courtCase.caseNumber,
    source: 'Putnam County Circuit Court (TN)',
    timestamp: courtCase.docketDate || new Date().toISOString(),
    title: `[${courtCase.caseType}] ${courtCase.caseNumber} - ${courtCase.status}`,
    content: formatCaseContent(courtCase),
    type: 'court_case',
    outcomes: [courtCase.status, courtCase.disposition || 'Pending'].filter(Boolean),
    reliability: courtCase.efileStatus ? 'high' : 'medium',
    jurisdiction: 'Putnam County, Tennessee'
  };
}

/**
 * Formats case content for CivicEntity
 */
function formatCaseContent(courtCase: CourtCase): string {
  const parts = [
    `${courtCase.caseType} Case #${courtCase.caseNumber}`,
    `Court: ${courtCase.court}`,
    `Judge: ${courtCase.judge}`,
    `Status: ${courtCase.status}`,
    `Disposition: ${courtCase.disposition || 'Pending'}`,
    `Docket Number: ${courtCase.docketNumber || 'N/A'}`,
    `Docket Date: ${courtCase.docketDate ? new Date(courtCase.docketDate).toLocaleDateString() : 'N/A'}`,
    `E-file Status: ${courtCase.efileStatus ? 'Electronic Filing' : 'Paper Filing'}`,
    `Plaintiff: ${courtCase.plaintiff || 'N/A'}`,
    `Defendant: ${courtCase.defendant || 'N/A'}`,
    `Attorney: ${courtCase.attorney || 'N/A'}`
  ];
  return parts.join('\n');
}

/**
 * Maps multiple court cases to CivicEntity array
 */
export function mapCourtCasesToCivicEntities(cases: CourtCase[]): CivicEntity[] {
  return cases.map(mapCourtCaseToCivicEntity);
}

/**
 * Validates CivicEntity structure
 */
export function validateCivicEntity(entity: CivicEntity): boolean {
  return !!(
    entity.id &&
    entity.source &&
    entity.timestamp &&
    entity.title &&
    entity.content &&
    entity.type &&
    entity.outcomes &&
    entity.reliability &&
    entity.jurisdiction
  );
}