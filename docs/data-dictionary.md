# Data dictionary

This schema covers the acquired full bank-additional variant and was checked against the bundled [UCI field notes acquisition](provenance.md). The [analytical contract](analytical-contract.md) groups fields by decision-time availability.

| Field | Type | Meaning and units | Availability for outreach decisions |
| --- | --- | --- | --- |
| age | Integer | Client age in years | Verify pre-call snapshot |
| job | Category | Occupation group, including unknown | Verify pre-call snapshot |
| marital | Category | Marital status, with divorced including widowed | Verify pre-call snapshot |
| education | Category | Education level, including unknown | Verify pre-call snapshot |
| default | Category | Credit in default, yes/no/unknown | Verify pre-call snapshot |
| housing | Category | Housing loan, yes/no/unknown | Verify pre-call snapshot |
| loan | Category | Personal loan, yes/no/unknown | Verify pre-call snapshot |
| contact | Category | Channel of last contact, cellular or telephone | Realized last-contact channel. A separately logged planned channel could be available earlier |
| month | Category | Last-contact month of year | Realized last-contact timing |
| day_of_week | Category | Last-contact weekday | Realized last-contact timing |
| duration | Integer | Last-call duration in seconds | After the call ends |
| campaign | Integer | Contacts with this client in the current campaign through and including the recorded last contact | Final count can incorporate contacts after the decision |
| pdays | Integer | Days since prior campaign contact, with 999 documented as no previous contact. The audit found conflicts with other history fields | Verify the reference date and availability when deciding |
| previous | Integer | Number of contacts before the current campaign | Candidate pre-call history |
| poutcome | Category | Prior campaign outcome, failure, nonexistent or success | Candidate pre-call history. Nonexistent is structural |
| emp.var.rate | Decimal | Employment variation rate, quarterly indicator | Confirm publication dates and values available at decision time |
| cons.price.idx | Decimal | Consumer price index, monthly indicator | Confirm publication dates and values available at decision time |
| cons.conf.idx | Decimal | Consumer confidence index, monthly indicator | Confirm publication dates and values available at decision time |
| euribor3m | Decimal | Three-month Euribor rate, daily indicator | Confirm availability at decision time |
| nr.employed | Decimal | Number of employees, quarterly indicator, reported scale | Confirm publication dates and values available at decision time |
| y | Category | Term-deposit subscription, yes/no. Target | Outcome known after outreach |
