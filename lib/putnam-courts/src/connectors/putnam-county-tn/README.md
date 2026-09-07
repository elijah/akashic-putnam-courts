# Putnam County TN Court Connector

## Overview
This connector provides structured access to Putnam County Circuit Court records through:
- [Official Court Clerk PDF Dockets](https://putnamtncourtclerk.gov/dockets/)
- Jurisdictional metadata
- CivicEntity-compliant output

## Key Features
- Civil/criminal/domestic case parsing
- E-file status tracking
- Jurisdiction validation
- Effortless integration with CivicEntity framework

## Installation
1. Install dependencies: `npm install cheerio node-fetch`
2. Configure API keys (if needed for future enhancements)
3. Usage: `const { scrapeCourtData } = require('./index')`

## Usage Example
```javascript
const { cases } = await scrapeCourtData();
console.log(cases.map(c => c.id)); // Output: ['2023-CCIV-001', '2023-CCRM-002']
```

## Validation
- All outputs comply with CivicEntity schema
- Disposition status validation
- Cross-references with TN Public Records Act

## Limitations
- PDF parsing requires updated regex patterns
- Limited to court clerk website content
- No live API (based on current public access)