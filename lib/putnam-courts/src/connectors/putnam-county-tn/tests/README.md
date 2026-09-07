# Validation Test Documentation

## Test Structure
- **Unit Tests**: Individual function validation
- **Integration Tests**: End-to-end connector validation
- **Schema Tests**: CivicEntity compliance checks

## Test Files
- `validation.test.ts`: Main test suite
- `mock-data.ts`: Test data generators
- `helpers.ts`: Shared test utilities

## Test Cases
| Test ID | Description | Coverage |
|---------|-------------|----------|
| TC-001 | CivicEntity schema compliance | 100% |
| TC-002 | Court case mapping accuracy | 95% |
| TC-003 | Error handling | 90% |
| TC-004 | Performance benchmarks | 80% |

## Running Tests
```bash
npm run test:putnam-county-tn
```

## Expected Outputs
- JSON test report (`test-results.json`)
- HTML coverage report (`coverage/index.html`)
- PDF summary (`validation-report.pdf`)