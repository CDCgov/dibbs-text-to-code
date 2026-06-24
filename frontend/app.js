// ── STEP INDICATOR (Upload → Review → Export) ──
function setStep(n) {
  document.querySelectorAll('#step-indicator .usa-step-indicator__segment').forEach(seg => {
    const s = Number(seg.dataset.step);
    seg.classList.toggle('usa-step-indicator__segment--complete', s < n);
    seg.classList.toggle('usa-step-indicator__segment--current', s === n);
  });
}
// Keep the indicator in sync with which testing sub-state is showing.
(function () {
  const valState = document.getElementById('validation-state');
  const sync = () => {
    if (valState.classList.contains('visible')) {
      const allReviewed = !document.getElementById('export-btn').disabled;
      setStep(allReviewed ? 3 : 2);
    } else {
      setStep(1);
    }
  };
  new MutationObserver(sync).observe(valState, { attributes: true, attributeFilter: ['class'] });
  new MutationObserver(sync).observe(document.getElementById('export-btn'), { attributes: true, attributeFilter: ['disabled'] });
})();

// ── TTC API ──
// 127.0.0.1 (not "localhost") avoids hitting any IPv6 service that may share port 8080.
const API_BASE = "http://127.0.0.1:8080";    // local FastAPI dev server (text_to_code_lambda.local_server)

async function fetchTTC(inputs, dataField) {
  const resp = await fetch(API_BASE + "/text-to-code", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ inputs, data_field: dataField }),
  });
  if (!resp.ok) throw new Error("HTTP " + resp.status);
  const data = await resp.json();
  return data.results || [];
}

// The data_field (DataField enum value) chosen via the radio toggle on each page.
function demoDataField() {
  return document.querySelector('input[name="demo-data-field"]:checked').value;
}
function testDataField() {
  return document.querySelector('input[name="test-data-field"]:checked').value;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// Render a code as a link to its loinc.org page (e.g. https://loinc.org/2339-0)
// when it's a LOINC code; otherwise just escaped text.
function loincCodeHtml(code, systemName) {
  const safe = escapeHtml(code);
  if (systemName === 'LOINC' && /^\d+-\d$/.test(String(code ?? "").trim())) {
    return `<a href="https://loinc.org/${encodeURIComponent(String(code).trim())}" target="_blank" rel="noopener">${safe}</a>`;
  }
  return safe;
}

// Pull the first column out of an uploaded CSV, dropping an optional header row.
function parseCsvFirstColumn(text) {
  const inputs = [];
  text.split(/\r?\n/).forEach(line => {
    if (!line.trim()) return;
    let firstCol;
    if (line[0] === '"') {
      const end = line.indexOf('"', 1);
      firstCol = end === -1 ? line.slice(1) : line.slice(1, end);
    } else {
      firstCol = line.split(",")[0];
    }
    inputs.push(firstCol.trim());
  });
  if (inputs.length && /^(input|lab.?test|test.?name|string|name|description)\b/i.test(inputs[0])) {
    inputs.shift();
  }
  return inputs.filter(Boolean);
}

// ── NAV ──
function showPage(page, btn) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-link').forEach(b => b.classList.remove('active'));
  document.getElementById('page-' + page).classList.add('active');
  btn.classList.add('active');
}

// ── DEMO ──
const demoChips = document.querySelectorAll('.chip');
demoChips.forEach(chip => {
  chip.addEventListener('click', () => {
    demoChips.forEach(c => c.classList.remove('selected'));
    chip.classList.add('selected');
    showDemoResult(chip.dataset.value, chip.dataset.code, chip.dataset.system, chip.dataset.systemName, chip.dataset.display, 'Lab test name');
  });
});

document.getElementById('demo-run-btn').addEventListener('click', async () => {
  const val = document.getElementById('demo-input').value.trim();
  if (!val) return;
  demoChips.forEach(c => c.classList.remove('selected'));
  const btn = document.getElementById('demo-run-btn');
  btn.disabled = true;
  btn.textContent = 'Running TTC…';
  try {
    const [r] = await fetchTTC([val], demoDataField());
    if (r && r.matched) {
      showDemoResult(r.input, r.code, r.code_system, r.code_system_name, r.display_name, 'Lab test name');
    } else {
      showDemoResult(val, 'No match', '—', '—', 'TTC did not return a confident code for this input.', 'Lab test name');
    }
  } catch (e) {
    showDemoResult(val, 'Error', '—', '—', 'Could not reach the TTC API at ' + API_BASE + ' (' + e.message + ').', 'Lab test name');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Run TTC';
  }
});

function showDemoResult(value, code, system, systemName, display, type) {
  document.getElementById('demo-result-input').textContent = value;
  document.getElementById('demo-result-code').innerHTML = loincCodeHtml(code, systemName);
  document.getElementById('demo-result-system').textContent = system;
  document.getElementById('demo-result-system-name').textContent = systemName;
  document.getElementById('demo-result-display').textContent = display;
  document.getElementById('demo-result-type').textContent = type;
  document.getElementById('demo-result-card').classList.add('visible');
}

// Show first chip result on load
showDemoResult('Glucose measurement', '2339-0', '2.16.840.1.113883.6.1', 'LOINC', 'Glucose [Mass/volume] in Blood', 'Lab test name');

// ── TESTING ──
// Seeded with examples for first paint; replaced by real API results after a CSV run.
let sampleRows = [
  { input: "Glucose measurement", code: "2339-0", systemName: "LOINC", display: "Glucose [Mass/volume] in Blood", system: "2.16.840.1.113883.6.1" },
  { input: "Flu A rapid test", code: "80382-5", systemName: "LOINC", display: "Influenza virus A Ag [Presence] in Upper respiratory specimen by Rapid immunoassay", system: "2.16.840.1.113883.6.1" },
  { input: "COVID-19 PCR", code: "94500-6", systemName: "LOINC", display: "SARS-CoV-2 (COVID-19) RNA [Presence] in Respiratory specimen by NAA with probe detection", system: "2.16.840.1.113883.6.1" },
  { input: "HDV IgG antibody, Blood", code: "35273-2", systemName: "LOINC", display: "Hepatitis D virus IgG Ab [Presence] in Serum by Immunoassay", system: "2.16.840.1.113883.6.1" },
  { input: "HbA1c", code: "4548-4", systemName: "LOINC", display: "Hemoglobin A1c/Hemoglobin.total in Blood", system: "2.16.840.1.113883.6.1" },
  { input: "TB skin test", code: "54454-4", systemName: "LOINC", display: "Tuberculin skin test reaction [Interpretation]", system: "2.16.840.1.113883.6.1" },
  { input: "Chlamydia urine NAA", code: "45084-1", systemName: "LOINC", display: "Chlamydia trachomatis DNA [Presence] in Urine by NAA with probe detection", system: "2.16.840.1.113883.6.1" },
  { input: "RPR syphilis screen", code: "20507-0", systemName: "LOINC", display: "Reagin Ab [Presence] in Serum by RPR", system: "2.16.840.1.113883.6.1" },
];

let rowStates = sampleRows.map(() => ({ status: 'pending', correctCode: '', possibleCode: '', notes: '' }));
let selectedTestType = 'Lab test name';
let uploadedInputs = [];

function selectTestType(btn, type) {
  document.querySelectorAll('#upload-state .type-btn:not(.coming-soon)').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  selectedTestType = type;
}

document.getElementById('csv-upload').addEventListener('change', function() {
  if (!this.files.length) return;
  const file = this.files[0];
  const reader = new FileReader();
  reader.onload = () => {
    uploadedInputs = parseCsvFirstColumn(reader.result);
    document.getElementById('upload-filename').textContent = file.name;
    document.getElementById('preview-filename').textContent = file.name;
    document.getElementById('preview-count').textContent = uploadedInputs.length + ' rows detected';
    document.getElementById('preview-body').innerHTML = uploadedInputs.map((s, i) =>
      `<tr><td class="num-cell">${i+1}</td><td>${escapeHtml(s)}</td></tr>`
    ).join('');
    document.getElementById('preview-card').classList.add('visible');
  };
  reader.readAsText(file);
});

document.getElementById('run-batch-btn').addEventListener('click', async () => {
  if (!uploadedInputs.length) { alert('Choose a CSV file with at least one row first.'); return; }
  const btn = document.getElementById('run-batch-btn');
  btn.disabled = true;
  btn.textContent = 'Running TTC…';
  try {
    const results = await fetchTTC(uploadedInputs, testDataField());
    sampleRows = results.map(r => ({
      input: r.input,
      code: r.matched ? r.code : '—',
      systemName: r.matched ? r.code_system_name : '—',
      display: r.matched ? r.display_name : 'No match',
      system: r.matched ? r.code_system : '—',
    }));
    rowStates = sampleRows.map(() => ({ status: 'pending', correctCode: '', possibleCode: '', notes: '' }));

    document.getElementById('upload-state').style.display = 'none';
    document.getElementById('validation-state').style.display = 'block';
    document.getElementById('validation-state').classList.add('visible');
    document.getElementById('validation-type-label').textContent = 'Data element type: ' + selectedTestType + ' · ' + testDataField();
    const name = document.getElementById('validator-name').value.trim();
    if (name) document.getElementById('validation-name-label').textContent = 'Validator: ' + name;
    buildValidationTable();
    updateProgress();
  } catch (e) {
    alert('Could not reach the TTC API at ' + API_BASE + ' (' + e.message + ').');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Run TTC on all rows';
  }
});

function buildValidationTable() {
  document.getElementById('validation-body').innerHTML = sampleRows.map((row, i) => `
    <tr id="row-${i}">
      <td class="num-cell">${i+1}</td>
      <td style="font-weight:600;">${escapeHtml(row.input)}</td>
      <td><div class="code-val">${loincCodeHtml(row.code, row.systemName)}</div><div class="code-sub">${escapeHtml(row.systemName)}</div></td>
      <td>${escapeHtml(row.systemName)}</td>
      <td style="max-width:220px; color:var(--base-darker);">${escapeHtml(row.display)}</td>
      <td style="min-width:260px;">
        <div class="action-group">
          <button class="act-btn act-correct" onclick="setStatus(${i},'correct')">✓ Correct</button>
          <button class="act-btn act-incorrect" onclick="setStatus(${i},'incorrect')">✗ Incorrect</button>
          <button class="act-btn act-uncertain" onclick="setStatus(${i},'uncertain')">? Uncertain</button>
        </div>
        <input class="sub-input sub-input-incorrect" id="correct-input-${i}" placeholder="Enter correct code..." oninput="rowStates[${i}].correctCode=this.value" />
        <input class="sub-input sub-input-uncertain" id="possible-input-${i}" placeholder="Enter possible code (optional)..." oninput="rowStates[${i}].possibleCode=this.value" />
      </td>
      <td style="min-width:160px;">
        <textarea class="notes-input" rows="2" placeholder="Add notes..." oninput="rowStates[${i}].notes=this.value"></textarea>
      </td>
      <td style="white-space:nowrap;"><span class="status-badge badge-pending" id="badge-${i}">Pending</span></td>
    </tr>
  `).join('');
}

function setStatus(i, status) {
  rowStates[i].status = status;
  const row = document.getElementById(`row-${i}`);
  const badge = document.getElementById(`badge-${i}`);
  const correctInput = document.getElementById(`correct-input-${i}`);
  const possibleInput = document.getElementById(`possible-input-${i}`);

  row.querySelectorAll('.act-btn').forEach(b => b.classList.remove('selected'));
  row.querySelector(`.act-${status}`).classList.add('selected');

  correctInput.classList.toggle('visible', status === 'incorrect');
  possibleInput.classList.toggle('visible', status === 'uncertain');
  if (status === 'incorrect') { correctInput.focus(); rowStates[i].possibleCode = ''; }
  else if (status === 'uncertain') { possibleInput.focus(); rowStates[i].correctCode = ''; }
  else { rowStates[i].correctCode = ''; rowStates[i].possibleCode = ''; }

  const map = { correct: ['badge-correct','✓ Correct'], incorrect: ['badge-incorrect','✗ Incorrect'], uncertain: ['badge-uncertain','? Uncertain'] };
  badge.className = 'status-badge ' + map[status][0];
  badge.textContent = map[status][1];
  row.classList.add('reviewed');
  updateProgress();
}

function updateProgress() {
  const total = rowStates.length;
  const correct = rowStates.filter(r => r.status === 'correct').length;
  const incorrect = rowStates.filter(r => r.status === 'incorrect').length;
  const uncertain = rowStates.filter(r => r.status === 'uncertain').length;
  const pending = rowStates.filter(r => r.status === 'pending').length;

  document.getElementById('progress-label').textContent = `${total - pending} of ${total} reviewed`;
  document.getElementById('count-correct').textContent = correct;
  document.getElementById('count-incorrect').textContent = incorrect;
  document.getElementById('count-uncertain').textContent = uncertain;
  document.getElementById('count-pending').textContent = pending;
  document.getElementById('fill-correct').style.width = (correct/total*100) + '%';
  document.getElementById('fill-incorrect').style.width = (incorrect/total*100) + '%';
  document.getElementById('fill-uncertain').style.width = (uncertain/total*100) + '%';

  const exportBtn = document.getElementById('export-btn');
  document.getElementById('export-label').textContent = pending === 0
    ? `All ${total} rows reviewed. Ready to export.`
    : `${pending} row${pending !== 1 ? 's' : ''} remaining before export.`;
  exportBtn.disabled = pending > 0;
}

document.getElementById('export-btn').addEventListener('click', () => {
  const headers = ['row','input_string','suggested_code','code_system_name','code_system','display_name','validation_status','correct_code','possible_code','notes'];
  const rows = sampleRows.map((r, i) => [
    i+1, `"${r.input}"`, r.code, r.systemName, r.system, `"${r.display}"`,
    rowStates[i].status, rowStates[i].correctCode || '', rowStates[i].possibleCode || '', `"${rowStates[i].notes || ''}"`
  ]);
  const csv = [headers, ...rows].map(r => r.join(',')).join('\n');
  const today = new Date().toISOString().slice(0,10);
  const safeName = (document.getElementById('validator-name').value.trim() || 'unknown').toLowerCase().replace(/\s+/g, '-');
  const safeType = selectedTestType.toLowerCase().replace(/\s+/g, '-');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
  a.download = `ttc_validation_${safeType}_${safeName}_${today}.csv`;
  a.click();
});
