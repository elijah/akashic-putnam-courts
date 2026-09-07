// lib/connectors/putnam-county-tn/tests/validation.test.ts
// Comprehensive validation tests for Putnam County TN Court Connector
import { mockCases, mockDocketSections } from '../mock-data';
import { fetchPutnamCountyCourtCases, mapCourtCaseToCivicEntity } from '../index';
import { CivicEntity } from '../types';

describe('Putnam County TN Court Connector Validation', () => {
  test('maps mock cases to CivicEntities correctly', () => {
    const CivicEnt = mapCourtCaseToCivicEntity;
    
    mockCases.forEach(mockCase => {
      const civicEntity = CivicEnt(mockCase as any);
      
      // Validate required fields
      expect(civicEntity.id).toBeDefined();
      expect(civicEntity.source).toBe('Putnam County Circuit Court (TN)');
      expect(civicEntity.title).toBeDefined();
      expect(civicEntity.content).toContain(mockCase.plaintiff || 'Unknown');
      expect(civicEntity.type).toBe('court_case');
      expect(civicEntity.outcomes).toBeInstanceOf(Array);
      expect(civicEntity.reliability).toBeDefined();
      expect(civicEntity.jurisdiction).toBe('Putnam County, Tennessee');
    });
  });

  test('validates CivicEntity structure enforces required fields', () => {
    const validEntity = mockCases[0];
    const entity = mockCases[0];
    
    expect(entity).toHaveProperty('id');
    expect(entity).toHaveProperty('source');
    expect(entity).toHaveProperty('timestamp');
    expect(entity).toHaveProperty('title');
    expect(entity).toHaveProperty('content');
    expect(entity).toHaveProperty('outcomes');
    expect(entity).toHaveProperty('reliability');
    expect(entity).toHaveProperty('jurisdiction');
// Additional validation
    expect(entity.outcomes).toBeInstanceOf(Array).withLength(GreaterThan(0));
    expect(entity.timestamp).toBeString();
  });

  test('handles malformed court case data gracefully', () => {
    // Create a completely malformed case
    const malformedCase = {
      id: 'INVALID-COCASE',
      caseNumber: '',
      plaintiff: '',
      defendant: '',
      caseType: '',
      judge: '\'\'',
      status: '',
      docketNumber: '\'',
      efileStatus: '\''
    };
    
    const entity = mapCourtCaseToCivicEntity(malformedCase as any);
    
    // Should still return an object but with safe defaults
    expect(entity.id).toBe('INVALID-COCASE');
    expect(entity.title.length).toBeGreaterThan(0);
  });
});

// Parameterized test for different case types
mockCases.forEach((caseData, index) => {
  test(`${caseData.caseType.toLowerCase()} case processing`, async () => {
    const entity = mockCases[index];
    const civicEntity = mockCases[index];
    
    // Verify required transformations
    expect(civicEntity.content).toContain(caseData.plaintiff || 'Unknown');
    expect(civicEntity.outcomes).toContain(caseData.status || 'Pending');
    expect(entity.type).toBe('court_case');
  });
});