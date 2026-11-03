const $ = s => document.querySelector(s);
let data;
async function load() {
  data = await (await fetch('/api/presets')).json();
  for (const preset of data.presets) {
    const option = document.createElement('option'); option.value = preset.id; option.textContent = preset.label;
    $('#preset-choice').append(option);
  }
  const b = data.benchmark;
  $('#preset-evidence').textContent = b.status === 'missing' ? 'MRV 분포 자료 미수집. 규모·증거금 가안은 설계 가정입니다.' :
    `MRV ${b.reporting_year} 컨테이너선 full 양수 보고 ${b.count.toLocaleString()}건: 25% ${Math.round(Number(b.quantiles['0.25'])).toLocaleString()}, 중앙 ${Math.round(Number(b.quantiles['0.5'])).toLocaleString()}, 75% ${Math.round(Number(b.quantiles['0.75'])).toLocaleString()} t CO₂. 제출 EUA나 회사 포지션이 아닙니다.`;
  $('#apply-preset').disabled = false;
}
$('#apply-preset').onclick = () => {
  const preset = data?.presets.find(x => x.id === $('#preset-choice').value);
  if (!preset) return;
  document.dispatchEvent(new CustomEvent('apply-carbon-preset', {detail:preset.inputs}));
  $('#preset-notice').textContent = `${preset.label}: ${preset.demand_eua.toLocaleString()} EUA 수요, ${preset.lots} lot. IM은 가정 5,000 EUR/lot, 현금 여유는 가정 명목의 10%입니다. ${data.notice}`;
};
$('#reset').addEventListener('click', () => {
  $('#preset-notice').textContent = '회사 실제 포지션이 아닌 거래 단위 가안입니다.';
});
load().catch(e => { $('#preset-evidence').textContent = e.message; });
