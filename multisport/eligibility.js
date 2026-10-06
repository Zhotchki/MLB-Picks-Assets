function offerUsable(row, data, now = Date.now()) {
  const snapshotAge = now - Date.parse(data.updatedAt);
  const offerAge = now - Date.parse(row.offerObservedAt);
  return Number.isFinite(snapshotAge) && snapshotAge >= 0 && snapshotAge <= 45 * 60000
    && Number.isFinite(offerAge) && offerAge >= 0 && offerAge <= 15 * 60000
    && Date.parse(row.startTime) > now
    && data.sports?.[row.sport]?.sourceStatus === 'CURRENT'
    && row.actionable === true && row.platform === 'Sleeper';
}
function eligibleSlips(data, size, now = Date.now()) {
  return (data.slips?.[size] || []).filter(s => s.legs?.length === Number(size)
    && s.legs.every(r => offerUsable(r, data, now)));
}
if (typeof module !== 'undefined') module.exports = {offerUsable, eligibleSlips};
