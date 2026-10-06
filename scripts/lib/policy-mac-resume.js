'use strict';
function resumeTime(value, now = Date.now()) {
  if (!value) return null;
  const time = Date.parse(value);
  if (!Number.isFinite(time) || time > now + 4 * 3600000) throw Error('invalid_resume_schedule');
  return time > now ? new Date(time).toISOString() : null;
}
module.exports = { resumeTime };
