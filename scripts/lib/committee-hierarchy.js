'use strict';
const TYPES = new Map([
  ['standing', 'standing'], ['subcommittee', 'subcommittee'], ['select', 'select'],
  ['special', 'special'], ['joint', 'joint'], ['commission or caucus', 'commission_or_caucus'],
  ['other', 'other'], ['task force', 'task_force'],
]);
function committeeHierarchy(value, congress, chamber, explicitParent) {
  const fields = {};
  const type = TYPES.get(String(value.type || value.committeeTypeCode || value.committeeType || '').toLowerCase());
  if (type) fields.committee_type = type;
  const code = String(value.systemCode || value.committeeCode || '').toLowerCase();
  // Senate's own committee classification distinguishes these from API Other.
  if (chamber === 'senate' && code === 'slia00') fields.committee_type = 'select';
  if (chamber === 'senate' && code === 'scnc00') fields.committee_type = 'caucus';
  if (value.isSubcommittee === true) fields.committee_type = 'subcommittee';
  const parents = Array.isArray(value.parent) ? value.parent : value.parent ? [value.parent] : [];
  const parent = parents.length === 1 ? parents[0] : null;
  const parentCode = parent?.systemCode || parent?.committeeCode;
  const parentChamber = String(parent?.chamber || chamber).toLowerCase();
  if (parentCode && parentChamber !== chamber) throw new Error('Committee parent chamber mismatch');
  const parentId = explicitParent || (parentCode ? `${congress}-${chamber}-${String(parentCode).toLowerCase()}` : null);
  if (parentId) {
    if (!parentId.startsWith(`${congress}-${chamber}-`)) throw new Error('Committee parent congress/chamber mismatch');
    if (!type || ['standing', 'subcommittee'].includes(type)) fields.committee_type = 'subcommittee';
    fields.parent_committee_id = parentId;
  }
  // Partial bill responses must not invent a type or erase a verified parent.
  // Only an authoritative non-subcommittee type establishes a top-level body.
  if (type && type !== 'subcommittee' && !parentId) fields.parent_committee_id = null;
  return fields;
}
module.exports = { committeeHierarchy };
