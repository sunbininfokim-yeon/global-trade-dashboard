'use strict';

// FederalRegister.gov provides a document agency's parent_id but not a
// cabinet/EOP/independent classification. Keep this mapping deliberately
// small and deterministic: it is a display taxonomy, not a legal assertion.

function normalizedAgencyName(agency) {
  const value = agency?.raw_name || agency?.name || agency?.short_name || '';
  return String(value).toLowerCase().replace(/&/g, ' and ')
    .replace(/[^a-z0-9]+/g, ' ').trim();
}

function federalRegisterParentId(agency) {
  const value = agency?.parent_id ?? agency?.parentId;
  if (value === null || value === undefined || value === '') return null;
  const number = Number(value);
  return Number.isInteger(number) && number > 0 ? number : null;
}

const EOP_NAMES = new Set([
  'executive office of the president',
  'office of management and budget',
  'office of the united states trade representative',
  'office of united states trade representative',
  'office of science and technology policy',
  'council of economic advisers',
  'national security council',
  'office of national drug control policy',
]);

const DEPARTMENT_NAMES = new Set([
  'department of state', 'state department',
  'department of the treasury', 'treasury department',
  'department of defense', 'defense department',
  'department of justice', 'justice department',
  'department of the interior', 'interior department',
  'department of agriculture', 'agriculture department',
  'department of commerce', 'commerce department',
  'department of labor', 'labor department',
  'department of health and human services', 'health and human services department',
  'department of housing and urban development', 'housing and urban development department',
  'department of transportation', 'transportation department',
  'department of energy', 'energy department',
  'department of education', 'education department',
  'department of veterans affairs', 'veterans affairs department',
  'department of homeland security', 'homeland security department',
]);

function classifyFederalAgency(agency) {
  // A Federal Register parent relationship is more specific than a name
  // match, so a child office is always shown below its parent in the UI.
  if (federalRegisterParentId(agency)) return 'sub';
  const name = normalizedAgencyName(agency);
  if (EOP_NAMES.has(name)) return 'eop';
  if (DEPARTMENT_NAMES.has(name)) return 'department';
  return 'independent';
}

module.exports = {
  classifyFederalAgency,
  federalRegisterParentId,
  normalizedAgencyName,
};
