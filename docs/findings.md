### Key Definitions

ICB stands for Integrated Care Boards - these are NHS organisations responsible for planning and commissioning health services for people living within a particular area. ICBs were established in July 2022 and replaced Clinical Commissioning Groups (CCGs).

Sub-ICB (also known as SICBL) stands for Sub-Integrated Care Board (Locations) - these represent local or district-level ICBs.

QOF stands for the Quality and Outcomes Framework. It is an annual incentive and reward scheme that financially compensates GP practices for delivering high-quality, evidence-based care to patients with chronic conditions.

A QOF disease register is a master list of all patients at a specific GP practice who have been diagnosed with a particular long-term health condition.

The Personal Demographics Service (PDS) is the national electronic master database that stores basic, non-clinical demographic details for all NHS patients in England, Wales, and the Isle of Man.

### June 2026 Data

The june 2026 data has these key files (row counts are not an indicator for said file type but moreso an observation of said release):

- nhs rate
  - the estimated diagnosis rate of dementia at varoius high-level boundaries
- - 750 rows
  - one row represents an estimated dementia diagnosis rate for a specific NHS geography, reporting period and population grouping
- local authority rate
  - the estimated diagnosis rate of dementia at a local authority level
  - circa 2300 rows
  - one row represents an estimated dementia diagnosis rate for a specific local authority, reporting period and population grouping
- gp-practice-level dementia data
  - detailed dementia diagnosis rates at a gp practice level
  - circa 43000 rows
  - one row represents a particular dementia-related measure for a specific GP practice, reporting period and combination of breakdown dimensions such as age, gender, ethnicity, dementia type or residential type
- sub-icb-level demenetia data
  - detailed dementia diagnosis rates at a sub-icb level
  - circa 12000 rows
  - one row represents a particular dementia-related measure for a specific Sub-ICB, reporting period and combination of breakdown dimensions
- mapping
  - location, geographic (ons), and icb details for gp practices
  - circa 6200 rows
  - one row represents a GP practice and its associated NHS and geographic identifiers, such as Sub-ICB, ICB and ONS geography codes

#### Measure Types

The data dictionary classifies various MEASURE types:

- DELIRIUM_12M
  - Number of patients with a recorded dementia diagnosis and a diagnosis of delirium recorded in the last 12-months
- FRAILTY (various)
  - Number of patients with a recorded dementia diagnosis who experienced a fall in the last X period
- INCIDENCE
  - Number of patients with a diagnosis of dementia which was recorded in the last quarter
- PALLIATIVE_CARE
  - Number of patients aged 65 and over with a recorded diagnosis of dementia and who are on the QOF palliative care register
- PRESCRIBING
  - Number of patients with a recorded dementia diagnosis who received a prescription of a certain medicine or have or haven't been deiganised with psychosis
- REFERRALS
  - Number of patients referred to, or the number of referrals to, a memory clinic within the last 12 months
- YOUNG_ONSET
  - Number of patients with a diagnosis of dementia recorded before the age of 65
- DEMENTIA_REGISTER
  - Number of patients recorded on the QOF Dementia Register, grouped by age, dementia type, ethincity, or residence type
- MCI
  - Number of patients with a diagnosis of mild cognitive impairment (MCI) at the reporting period end date for the age and gender category defined in columns AGE and GENDER
- PAT_LIST
  - Registered patients for the age and gender defined in columns AGE and GENDER. This data comes from the Personal Demographics Service (PDS) dataset.

#### Initial interpretations

- `MEASURE` defines **what is being counted or measured** , while fields such as `AGE`, `GENDER`, `ETHNICITY`, `DEMENTIA_TYPE` and `RESIDENTIAL_TYPE` provide the context or breakdown for that measure.
- Not every measure uses every breakdown column. Some dimensions are therefore expected to be blank depending on the `MEASURE`.
- `VALUE` should not be interpreted in isolation. Its meaning depends on the corresponding `MEASURE`, `BREAKDOWN` and other populated dimension fields.
- `PAT_LIST` appears to provide the registered patient population for particular age and gender groups. This means it can potentially act as a **denominator or population context** for other measures rather than representing dementia cases itself.
- `DEMENTIA_REGISTER` represents people recorded on the QOF Dementia Register and therefore gives a measure of **recorded diagnosed dementia** , rather than the estimated total number of people who may have dementia.
- The estimated diagnosis-rate files are conceptually different from the GP/Sub-ICB measure files. The rate files appear to compare **recorded dementia diagnoses against an estimated dementia population** , whereas the detailed files primarily contain counts and characteristics of recorded patients and activity.
- `MCI` is related to dementia analysis but is not itself a dementia diagnosis. It describes people recorded with mild cognitive impairment, so it should probably remain conceptually separate from the dementia register.
- `INCIDENCE` is different from prevalence/register counts because it represents **newly recorded dementia diagnoses within a period** , rather than everyone currently recorded with dementia.
- Measures such as prescribing, referrals, delirium and palliative care describe **care, treatment or associated clinical characteristics** of people with dementia rather than the core size of the diagnosed dementia population.
- The mapping file is important because the detailed GP-level data does not need to repeat every higher-level geographic attribute. Practice codes can instead be linked through the mapping table to Sub-ICBs, ICBs and geographic areas.
