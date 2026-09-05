'use strict';

const assert = require('node:assert/strict');
const { parseExecutiveOrderAgencyDirectives } = require('./eo-agency-directives');

const agencies = [
  { agency_id: 'fr-department-of-commerce', name: 'Department of Commerce' },
  { agency_id: 'fr-department-of-state', name: 'Department of State' },
  { agency_id: 'fr-department-of-justice', name: 'Department of Justice' },
];

const relations = parseExecutiveOrderAgencyDirectives(
  'The Secretary of Commerce shall establish the program, in consultation with the Secretary of State and in coordination with the Attorney General.',
  agencies,
);

assert.deepEqual(relations.map((relation) => [relation.agency_id, relation.relationship_type]), [
  ['fr-department-of-commerce', 'directed_agency'],
  ['fr-department-of-state', 'consulted_agency'],
  ['fr-department-of-justice', 'coordinating_agency'],
]);
assert.match(relations[0].evidence_excerpt, /Secretary of Commerce shall/i);

assert.deepEqual(parseExecutiveOrderAgencyDirectives('The Department of Commerce supports this order.', agencies), []);

console.log('EO agency directive parser tests passed');
