'use strict';
// Unknown is deliberately different from active: both block writes, but a
// temporary GitHub outage must not permanently terminate the local supervisor.
function remoteState(workflow, runs) {
  if (!workflow || !Array.isArray(runs) || !workflow.state || runs.some(r=>!r.status)) return 'unknown';
  return workflow.state==='disabled_manually' && runs.every(r=>r.status==='completed') ? 'safe' : 'active';
}
module.exports={remoteState};
