/* Metaphor review app — ONE page for every language and every stage.
 *
 * The page carries no data of its own. It renders a "review bundle" (JSON written by
 * review_page.py): either embedded in the page (<script id="bundle" type="application/json">,
 * the public English demo) or chosen by the reviewer through the file picker on the start
 * screen (the private Danish and Dutch lists). The bundle's `lang` selects the UI language,
 * and everything else — provenance, tables, plant check, candidates — comes from the bundle.
 *
 * Nothing leaves the browser: the file is read with FileReader, labels autosave to
 * localStorage, and the export is a download of ids + verdicts only.
 */
(function () {
  'use strict';
  const I18N = JSON.parse(document.getElementById('i18n').textContent);
  let LANG = 'en', T = I18N.en;
  const VERDICTS = ['yes', 'maybe', 'no', 'unsure'];

  function t(key, vars) {
    let s = T[key]; if (s === undefined) s = I18N.en[key]; if (s === undefined) return key;
    if (Array.isArray(s)) return s;
    if (vars) for (const k in vars) s = s.split('{' + k + '}').join(vars[k]);
    return s;
  }
  function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
  function num(n) { try { return Number(n).toLocaleString(LANG === 'en' ? 'en-GB' : LANG); } catch (e) { return String(n); } }
  function pct(x, d) { return (d === undefined ? Number(x).toFixed(1) : Number(x).toFixed(d)) + '%'; }
  function setLang(l) { LANG = I18N[l] ? l : 'en'; T = I18N[LANG]; document.documentElement.lang = LANG; }
  function browserLang() { const l = ((navigator.language || 'en').slice(0, 2)).toLowerCase(); return I18N[l] ? l : 'en'; }

  // Official 4D PICTURE icon, kept inline so the review page remains self-contained and
  // makes no network request when a reviewer opens it.
  function projectMark() {
    return `<svg class="project-logo" viewBox="0 0 127.854 101.619" aria-hidden="true" focusable="false"><path d="M671.28,254.561H641.325V291.6a3.575,3.575,0,1,0,7.15,0V261.712h22.8a20.643,20.643,0,0,1,20.618,20.62V328.4a20.642,20.642,0,0,1-20.62,20.62H635.415a.205.205,0,0,1-.205-.2v-84.5a9.742,9.742,0,0,0-17.493-5.905l-44.525,57.682a9.737,9.737,0,0,0,7.645,15.634l0,.007h36.591a3.575,3.575,0,1,0,0-7.15H580.948a2.592,2.592,0,0,1-2.068-4.156L623.4,262.747a2.436,2.436,0,0,1,2-1.03,2.857,2.857,0,0,1,.888.143,2.521,2.521,0,0,1,1.764,2.458v84.5a7.364,7.364,0,0,0,7.356,7.354h35.864a27.8,27.8,0,0,0,27.77-27.77V282.332A27.8,27.8,0,0,0,671.28,254.561Z" transform="translate(-571.195 -254.556)"/></svg>`;
  }
  function euMark() {
    const points = [[27,7],[32.5,8.47],[36.53,12.5],[38,18],[36.53,23.5],[32.5,27.53],[27,29],[21.5,27.53],[17.47,23.5],[16,18],[17.47,12.5],[21.5,8.47]];
    return `<svg class="eu-logo" viewBox="0 0 54 36" aria-hidden="true" focusable="false"><rect width="54" height="36" rx="1.5"/><g>${points.map(([x, y]) => `<path d="M0-3 .7-1 2.85-.93 1.14.37 1.76 2.43 0 1.2-1.76 2.43-1.14.37-2.85-.93-.7-1Z" transform="translate(${x} ${y}) scale(.62)"/>`).join('')}</g></svg>`;
  }
  function siteHeader(controls, actionClass) {
    return `<header class="site-header" aria-label="${esc(t('header_label'))}">
  <a class="brand" href="https://4dpicture.eu/" target="_blank" rel="noopener noreferrer" aria-label="${esc(t('project_site'))}">
    <span class="project-logo-wrap">${projectMark()}</span><span class="brand-copy"><strong>4D PICTURE <span class="brand-tool">/ ${esc(t('brand'))}</span></strong><small>${esc(t('project_work_package'))}</small></span>
  </a>
  <div class="header-actions${actionClass ? ' ' + esc(actionClass) : ''}">${controls || ''}</div>
</header>`;
  }
  function projectContext() {
    return `<aside class="project-context" aria-label="${esc(t('project_context_label'))}">
  <span class="project-context-number" aria-hidden="true">WP3</span>
  <div class="project-context-copy"><strong>${esc(t('project_context_title'))}</strong><p>${esc(t('project_context_text'))}</p></div>
  <a class="project-context-link" href="https://4dpicture.eu/workpackage/text-mining-and-citizen-science/" target="_blank" rel="noopener noreferrer">${esc(t('project_link'))} <span aria-hidden="true">&#8599;</span></a>
</aside>`;
  }
  function siteFooter() {
    return `<footer class="site-footer">
  <div class="funding-mark">${euMark()}<div><strong>${esc(t('funding_title'))}</strong><span>${esc(t('funding_reference'))}</span></div></div>
  <div class="footer-links"><a href="https://4dpicture.eu/" target="_blank" rel="noopener noreferrer">${esc(t('project_site'))}</a><a href="https://4dpicture.eu/workpackage/text-mining-and-citizen-science/" target="_blank" rel="noopener noreferrer">${esc(t('project_link'))}</a></div>
  <p class="footer-disclaimer">${esc(t('funding_disclaimer'))}</p>
  <p class="footer-privacy">${esc(t('footer'))}</p>
</footer>`;
  }

  // ------------------------------------------------------------------ start screen ---
  function renderLoader(lang, error) {
    setLang(lang);
    document.body.className = 'review-page loader-page';
    document.title = t('app_title');
    const langs = Object.keys(I18N).map(l =>
      `<button type="button" class="langbtn${l === LANG ? ' on' : ''}" data-lang="${l}">${esc(I18N[l].lang_name)}</button>`).join('');
    document.getElementById('app').innerHTML = `
${siteHeader(`<span class="langswitch" role="group" aria-label="${esc(t('language_label'))}">${langs}</span>`, 'language-actions')}
${projectContext()}
<section class="loader">
  <p class="eyebrow">${esc(t('loader_eyebrow'))}</p>
  <h1>${esc(t('loader_title'))}</h1>
  <p class="lede">${esc(t('loader_lede'))}</p>
  ${error ? `<div class="note loader-error" role="alert">${esc(t('loader_error'))}</div>` : ''}
  <div class="dropzone" id="drop">
    <label class="button primary filebtn">${esc(t('loader_button'))}<input type="file" id="file" accept=".json,application/json"></label>
    <span class="drophint">${esc(t('loader_drop'))}</span>
  </div>
  <ol class="loader-steps">
    <li><b>1</b><div><strong>${esc(t('loader_step1'))}</strong><p>${esc(t('loader_step1_text'))}</p></div></li>
    <li><b>2</b><div><strong>${esc(t('loader_step2'))}</strong><p>${esc(t('loader_step2_text'))}</p></div></li>
    <li><b>3</b><div><strong>${esc(t('loader_step3'))}</strong><p>${esc(t('loader_step3_text'))}</p></div></li>
  </ol>
  <p class="privacy">${esc(t('loader_privacy'))}</p>
</section>
${siteFooter()}`;
    document.querySelectorAll('.langbtn').forEach(b => b.onclick = () => renderLoader(b.dataset.lang, false));
    const inp = document.getElementById('file');
    inp.onchange = () => { if (inp.files[0]) loadFile(inp.files[0]); };
    const drop = document.getElementById('drop');
    drop.ondragover = ev => { ev.preventDefault(); drop.classList.add('over'); };
    drop.ondragleave = () => drop.classList.remove('over');
    drop.ondrop = ev => { ev.preventDefault(); drop.classList.remove('over'); const f = ev.dataTransfer.files[0]; if (f) loadFile(f); };
  }

  function loadFile(file) {
    const rd = new FileReader();
    rd.onload = () => {
      let B = null;
      try { B = JSON.parse(rd.result); } catch (e) { B = null; }
      if (B && B.format === 'metaphor-review-bundle-encrypted') { renderPassScreen(B, file.name, ''); return; }
      if (!B || B.format !== 'metaphor-review-bundle' || !Array.isArray(B.rows)) { renderLoader(LANG, true); return; }
      B._fromFile = true;
      render(B);
      window.scrollTo(0, 0);
    };
    rd.readAsText(file);
  }

  // ---- encrypted lists: PBKDF2-SHA256 → AES-256-GCM, decrypted here with WebCrypto ----
  function b64(s) { const bin = atob(s); const u = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i); return u; }
  async function decryptBundle(E, pass) {
    const enc = new TextEncoder();
    const km = await crypto.subtle.importKey('raw', enc.encode(pass.normalize('NFKC').trim()), 'PBKDF2', false, ['deriveKey']);
    const key = await crypto.subtle.deriveKey({ name: 'PBKDF2', salt: b64(E.kdf.salt), iterations: E.kdf.iterations, hash: E.kdf.hash },
      km, { name: 'AES-GCM', length: 256 }, false, ['decrypt']);
    const pt = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: b64(E.cipher.iv) }, key, b64(E.data));
    return JSON.parse(new TextDecoder().decode(pt));
  }
  function renderPassScreen(E, fname, error) {
    setLang(E.lang);
    document.body.className = 'review-page loader-page';
    document.title = t('app_title');
    const noCrypto = !(window.crypto && crypto.subtle);
    document.getElementById('app').innerHTML = `
${siteHeader(`<button type="button" class="button secondary" id="reload">${esc(t('loader_other'))}</button>`)}
${projectContext()}
<section class="loader">
  <p class="eyebrow">${esc(t('pass_eyebrow'))}</p>
  <h1>${esc(t('pass_title'))}</h1>
  <p class="lede">${esc(t('pass_lede', { file: fname }))}</p>
  ${E.corpus ? `<p class="lede"><strong>${esc(E.corpus)}</strong> · <code>${esc(E.list_id || '')}</code></p>` : ''}
  ${error ? `<div class="note loader-error" role="alert">${esc(error)}</div>` : ''}
  ${noCrypto ? `<div class="note loader-error" role="alert">${esc(t('pass_nocrypto'))}</div>` : `
  <form id="passform" class="passform">
    <label>${esc(t('pass_label'))} <input id="pass" type="password" autocomplete="off" autocapitalize="off" spellcheck="false" size="32" autofocus></label>
    <label class="showpass"><input type="checkbox" id="passshow"> ${esc(t('pass_show'))}</label>
    <button type="submit" class="button primary" id="passgo">${esc(t('pass_button'))}</button>
  </form>`}
  <p class="privacy">${esc(t('loader_privacy'))}</p>
</section>
${siteFooter()}`;
    document.getElementById('reload').onclick = () => renderLoader(LANG, false);
    const f = document.getElementById('passform'); if (!f) return;
    document.getElementById('passshow').onchange = ev => { document.getElementById('pass').type = ev.target.checked ? 'text' : 'password'; };
    f.onsubmit = async ev => {
      ev.preventDefault();
      const btn = document.getElementById('passgo'); btn.disabled = true;
      try {
        const B = await decryptBundle(E, document.getElementById('pass').value);
        if (!B || B.format !== 'metaphor-review-bundle' || !Array.isArray(B.rows)) throw new Error('not a bundle');
        B._fromFile = true; render(B); window.scrollTo(0, 0);
      } catch (e) { renderPassScreen(E, fname, t('pass_error')); }
    };
  }

  // ---------------------------------------------------------------------- helpers ---
  function highlight(text, phrase) {
    const e = esc(text), ph = String(phrase || '').trim();
    if (ph.length < 3) return e;
    const words = esc(ph).split(/\s+/).map(w => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
    try { return e.replace(new RegExp('(' + words.join('\\s+') + ')', 'i'), '<mark>$1</mark>'); }
    catch (err) { return e; }
  }
  function statsRow(label, s, hi, full) {
    return `<tr${hi ? " class='hi'" : ''}><td>${esc(label)}</td><td>${num(s.n)}</td><td>${pct(s.keep, hi ? 0 : 1)}</td>`
      + `<td>${pct(s.exp, hi ? 0 : 1)}</td><td>${num(s.median)}</td>`
      + (full ? `<td>${pct(s.top10, hi ? 0 : 1)}</td><td>${pct(s.bottom, hi ? 0 : 1)}</td>` : '') + '</tr>';
  }

  // ------------------------------------------------------------------ page blocks ---
  function header(B, blind) {
    const tag = B.header_tag || ((blind ? t('header_tag_blind') : t('header_tag_ranked')) + (B.private ? t('header_tag_private') : ''));
    return siteHeader(`<span class="header-tag">${esc(tag)}</span>${B._fromFile ? `<button type="button" class="button secondary" id="reload">${esc(t('loader_other'))}</button>` : ''}`);
  }
  function stageStrip(stage) {
    const cur = { filter: 1, vote: 2, explore: 3 }[stage];
    return '<nav class="stages">' + [1, 2, 3].map(n =>
      `<span class="st${n === cur ? ' cur' : ''}"><b>${n}</b> ${esc(t('stage_' + n))}<small>${esc(t('stage_' + n + '_who'))}</small></span>`).join('') + '</nav>';
  }
  function hero(B) {
    const pub = B.private ? '' : t('hero_public');
    return `<section class="rank-hero"><div>
    <p class="eyebrow">${esc(t('hero_eyebrow'))}</p><h1>${esc(t('hero_title'))}</h1>
    <p class="hero-lede">${esc(t('hero_lede', { pub }))}</p>
    <div class="hero-actions"><a class="button primary" href="#candidates">${esc(t('hero_browse'))} <span aria-hidden="true">&#8595;</span></a>
      <button class="button secondary" id="labelToggle" type="button" aria-pressed="false">${esc(t('hero_label_on'))}</button></div></div>
  <div class="rank-metrics"><div class="rank-metric"><strong>${num(B.rows.length)}</strong><span>${esc(t('metric_candidates', { pub }))}</span></div>
    <div class="rank-metric"><strong>${num(B.tier_counts ? B.tier_counts[0] : 0)}</strong><span>${esc(t('metric_tier0'))}</span></div>
    <div class="rank-metric"><strong>${num(B.counts.n_plants_in_rows)}</strong><span>${esc(t('metric_plants'))}</span></div></div></section>`;
  }
  function rankLogic(B) {
    if (!B.tier_counts) return '';
    const ex = (B.category_top || []).map(([n, c]) => `<span>${esc(n)} <b>${c}</b></span>`).join('');
    return `<section class="rank-logic"><div><p class="eyebrow">${esc(t('rl_eyebrow'))}</p><h2>${esc(t('rl_title'))}</h2><p>${esc(t('rl_text'))}</p></div>
  <div class="output-routes"><div class="rank-route"><span class="route-label">${esc(t('rl_ranked'))}</span><ol class="tier-key">
    <li class="tier-top"><span>${esc(t('rl_first'))}</span><strong>${num(B.tier_counts[0])}</strong><p>${esc(t('tier_0'))}</p></li>
    <li><span>${esc(t('rl_next'))}</span><strong>${num(B.tier_counts[1])}</strong><p>${esc(t('tier_1'))}</p></li>
    <li><span>${esc(t('rl_last'))}</span><strong>${num(B.tier_counts[2])}</strong><p>${esc(t('tier_2_pl'))}</p></li></ol></div>
    <a class="category-route" href="#veh"><span class="route-label">${esc(t('rl_category'))}</span><strong>${esc(t('rl_recurring'))}</strong><p>${esc(t('rl_freq'))}</p>
      <div class="category-preview">${ex}</div><span class="route-link">${esc(t('rl_browse'))} &#8595;</span></a></div>
  ${B.private ? '' : `<a class="rank-method-link" href="index.html#approach">${esc(t('rl_method'))} <span aria-hidden="true">&#8594;</span></a>`}</section>`;
  }
  function statusBlock(B) {
    const ranked = B.ranked_page ? `<a href="${esc(B.ranked_page)}">${esc(t('ranked_link'))}</a>` : t('stage3');
    return `<div class="status"><div class="l1">${t('status_' + B.stage + '_1')}</div><div class="l2">${t('status_' + B.stage + '_2')}</div><div class="l3">${t('status_' + B.stage + '_3', { ranked })}</div></div>`;
  }
  function howBox(B) {
    const c = B.counts, data = esc((B.source_note || B.corpus).replace(/\.$/, ''));
    const purpose = t('purpose_' + B.stage, { data });
    let lede;
    if (B.stage === 'filter') lede = t('lede_filter', {
      stream: B.stream ? t('lede_stream', { stream: B.stream_label || B.stream }) : '', n: num(c.n_rows),
      folded: c.n_folded ? t('lede_folded', { m: num(c.n_folded) }) : '' });
    else if (B.stage === 'vote') lede = t('lede_vote', { n: num(c.n_rows) });
    else lede = t('lede_explore', { N: num(c.n_total), note: esc(B.source_note || '') });
    const steps = (B.provenance_steps || []).slice();
    if (steps.length) {
      if (B.stage === 'filter') steps.push(t('how_filter', {
        page: B.stream ? t('how_filter_stream', { stream: B.stream_label || B.stream }) : t('how_filter_page'),
        top: num(c.n_top), deep: num(c.n_deep), n: num(c.n_rows) }));
      else if (B.stage === 'vote') steps.push(t('how_vote', { n: num(c.n_rows) }));
      else steps.push(t('how_explore', { N: num(c.n_total) }));
    }
    return `<details id="how"${B.stage !== 'explore' ? ' open' : ''}><summary>${esc(steps.length ? t('how_summary') : t('how_summary_short'))}</summary>
  <div id="purpose">${purpose}</div><p class="lede">${lede}</p>${steps.length ? '<ol>' + steps.map(s => `<li>${esc(s)}</li>`).join('') + '</ol>' : ''}</details>`;
  }
  function raterBox(B) {
    const def = { vote: 'ppi', filter: 'researcher', explore: '' }[B.stage];
    const opts = (def ? '' : `<option value="">${esc(t('role_choose'))}</option>`) + ['ppi', 'researcher', 'clinician', 'other'].map(v =>
      `<option value="${v}"${v === def ? ' selected' : ''}>${esc(t('role_' + v))}</option>`).join('');
    return `<div id="rater"><strong>${esc(B.stage === 'explore' ? t('rater_heading_explore') : t('rater_heading'))}</strong><br>
  <label>${esc(t('rater_name'))} <input id="rname" placeholder="${esc(t('rater_name_ph'))}" size="18"></label>
  <label>${esc(t('rater_role'))} <select id="rrole">${opts}</select></label>
  <span id="rstate" style="color:var(--mut);font-size:13px"></span>
  <p class="lede" style="margin:8px 0 0">${t('rater_privacy')}</p></div>`;
  }
  function behaved(B) {
    const S = B.stats; if (!S) return '';
    let h = `<h2>${esc(t('behaved_heading'))}</h2><div class="tw"><table><tr><th></th><th>${esc(t('th_items'))}</th><th>${esc(t('th_keep'))}</th><th>${esc(t('th_exp'))}</th><th>${esc(t('th_median'))}</th><th>${esc(t('th_top10'))}</th><th>${esc(t('th_bottom'))}</th></tr>`;
    if (S.plant) h += statsRow(t('plant_row'), S.plant, true, true);
    h += statsRow(t('pool_row'), S.pool, false, true) + '</table></div>';
    return h;
  }
  function plantBlock(B) {
    const P = B.plants; if (!P || !B.stats || !B.stats.plant) return '';
    const excl = P.excl_entries && P.excl_entries.length ? t('plant_excl', {
      k: P.excl_entries.length, rows: P.excl_rows ? t('plant_excl_rows', { rows: num(P.excl_rows) }) : '' }) : '';
    let h = `<h2>${esc(t('plant_heading'))}</h2><p class="lede">${t('plant_text', {
      kind: LANG === 'en' && !B.translated_plants ? t('plant_kind_published') : t('plant_kind_translated'),
      nl_note: B.lang === 'nl' ? t('plant_nl_note') : '', n_entries: num(P.n_entries), median: num(B.stats.plant.median),
      N: num(P.N), excl })}</p>`;
    if (P.ranks && P.ranks.length) {
      const W = 760, LX = 90, RX = 740, N = Math.max(2, P.N);
      const sx = r => LX + Math.log(Math.max(1, r)) / Math.log(N) * (RX - LX);
      const ticks = [1, 10, 100, 1000, 10000, 100000].filter(x => x < N).map(x =>
        `<line x1="${sx(x).toFixed(0)}" y1="26" x2="${sx(x).toFixed(0)}" y2="96" class="grid"/><text x="${sx(x).toFixed(0)}" y="115" class="tick">${num(x)}</text>`).join('')
        + `<line x1="${RX}" y1="26" x2="${RX}" y2="96" class="grid"/><text x="${RX}" y="115" class="tick">${num(N)}</text>`;
      const dots = P.ranks.map(([id, r, ph]) => `<circle cx="${sx(r).toFixed(1)}" cy="60" r="6" class="dot held"><title>${esc(id)} · #${num(r)} · ${esc(ph || '')}</title></circle>`).join('');
      h += `<h2>${esc(t('plant_strip_heading'))}</h2><p class="lede">${esc(t('plant_strip_lede', { N: num(P.N) }))}</p>
  <figure class="plantstrip"><svg viewBox="0 0 ${W} 124" role="img" aria-label="${esc(t('plant_strip_heading'))}"><text x="${LX - 8}" y="64" class="lane">${esc(t('plant_strip_lane'))}</text>${ticks}${dots}</svg></figure>
  <div class="tw"><table><tr><th>#</th><th>${esc(t('th_median'))}</th><th></th></tr>${P.ranks.slice().sort((a, b) => a[1] - b[1]).map(([id, r, ph]) =>
        `<tr><td>${esc(id)}</td><td>${num(r)}</td><td style="text-align:left">${esc(ph || '')}</td></tr>`).join('')}</table></div>`;
    }
    return h;
  }
  function provBlock(B) {
    if (!B.has_old) return '';
    return `<h2>${esc(t('prov_heading'))}</h2><p class="lede">${t('prov_text', { old: esc(B.old_label), n: num(B.rows.length - B.counts.n_plants_in_rows), both: num(B.n_old), new: num(B.n_new) })}</p>`;
  }
  function byStratum(B) {
    const S = B.stats; if (!S || !S.by_stratum) return '';
    return `<h2>${esc(t('by', { noun: B.stratum_noun }))}</h2><div class="tw"><table><tr><th>${esc(B.stratum_noun)}</th><th>${esc(t('th_items'))}</th><th>${esc(t('th_keep'))}</th><th>${esc(t('th_exp'))}</th><th>${esc(t('th_median'))}</th></tr>`
      + S.by_stratum.map(([name, s]) => statsRow(name, s, false, false)).join('') + '</table></div>';
  }
  function scoreNote(B) {
    const S = B.stats; if (!S || S.score_mean === undefined) return '';
    return `<div class="note">${t('score_note', { mean: Number(S.score_mean).toFixed(2), median: Number(S.score_median).toFixed(1) })}</div>`;
  }
  function vehSection(B) {
    const cov = B.layers_cov || {}; if (!Object.values(cov).some(v => v)) return '';
    const opts = [['usas', cov.usas], ['veh', cov.usas], ['head', cov.head], ['wn1', cov.wn1], ['wn2', cov.wn2], ['fn', cov.fn], ['llm', cov.llm], ['llm_c1', cov.llm_c1], ['llm_c2', cov.llm_c2]];
    const top = cov.usas ? 'veh' : (cov.head ? 'head' : '');
    const sel = opts.map(([k, n]) => `<option value="${k}"${n ? '' : ' disabled'}${k === top ? ' selected' : ''}>${esc(t('layer_' + k))}${n ? '' : esc(t('veh_not_computed'))}</option>`).join('');
    const sel2 = `<option value="">${esc(t('veh_nothing'))}</option>` + opts.filter(([k]) => k !== 'usas').map(([k, n]) =>
      `<option value="${k}"${n ? '' : ' disabled'}>${esc(t('layer_' + k))}</option>`).join('');
    const fam = (B.fam && B.fam[1]) ? `<div class="ctlrow"><label>${esc(t('veh_from_model'))} <select id="vfam"><option value="a">${esc(B.fam[0])}</option><option value="b">${esc(B.fam[1])}</option><option value="agree">${esc(t('veh_agree', { n: num(B.n_agree || 0) }))}</option></select></label></div>` : '';
    return `<div id="veh"><h2>${esc(t('veh_heading'))}</h2><p class="lede">${t('veh_lede')}</p>
  <div id="vehctl">${fam}<div class="ctlrow"><label>${esc(t('veh_groupby'))} <select id="vlayer">${sel}</select></label>
  <label>${esc(t('veh_thenby'))} <select id="vlayer2">${sel2}</select></label>
  <label>${esc(t('veh_top'))} <input id="vtop" type="number" min="1" max="${B.rows.length}" value="${B.rows.length}" size="5"> ${esc(t('veh_of', { n: num(B.rows.length) }))}</label>
  <span id="vcov" style="color:var(--mut)"></span><button id="vclear">${esc(t('veh_clear'))}</button></div></div>
  <div class="tw"><table id="vtab"></table></div></div>`;
  }
  function bar(B, blind) {
    let f;
    if (blind) f = '<span style="display:none"><select id="fs"></select><select id="ft"></select><select id="fp"></select><select id="fm"></select><select id="fv"></select><select id="fc"></select></span>';
    else {
      f = `<label>${esc(B.stratum_noun)} <select id="fs"><option value="">${esc(t('f_all'))}</option>${(B.strata || []).map(s => `<option value="${esc(s)}">${esc(s)}</option>`).join('')}</select></label>`
        + `<label>${esc(t('f_screen'))} <select id="ft"><option value="">${esc(t('f_all'))}</option><option value="0">${esc(t('tier_0'))}</option><option value="1">${esc(t('tier_1'))}</option><option value="2">${esc(t('tier_2_pl'))}</option></select></label>`
        + ((B.veh_cats || []).length ? `<label>${esc(t('f_domain'))} <select id="fv"><option value="">${esc(t('f_all'))}</option>${B.veh_cats.map(([k, c]) => `<option value="${esc(k)}">${esc(k)} (${c})</option>`).join('')}</select></label>` : '')
        + ((B.veh_codes || []).length ? `<label>${esc(t('f_code'))} <select id="fc"><option value="">${esc(t('f_all'))}</option>${B.veh_codes.map(([k, d, c]) => `<option value="${esc(k)}">${esc(k)} — ${esc(d)} (${c})</option>`).join('')}</select></label>` : '')
        + (B.simile ? `<label>${esc(t('f_expr'))} <select id="fm"><option value="">${esc(t('f_all'))}</option><option value="1">${esc(t('f_marker'))}</option><option value="0">${esc(t('f_nomarker'))}</option></select></label>` : '')
        + `<label>${esc(t('f_prov'))} <select id="fp"><option value="">${esc(t('f_all'))}</option><option value="new">${esc(t('f_prov_new'))}</option><option value="both">${esc(t('f_prov_both', { old: B.old_label || '' }))}</option><option value="plant">${esc(t('f_prov_plant'))}</option></select></label>`;
    }
    return `<div id="bar">${f}<label>${esc(t('f_show'))} <select id="fl"><option value="">${esc(t('f_everything'))}</option><option value="todo">${esc(t('f_todo'))}</option><option value="yes">${esc(t('f_yes'))}</option><option value="maybe">${esc(t('f_maybe'))}</option></select></label>
  <label>${esc(t('f_search'))} <input id="fq" placeholder="${esc(t('f_search_ph'))}" size="14"></label>
  <button id="fr">${esc(t('f_reset'))}</button><button id="ex">${esc(t('f_export'))}</button><span id="count"></span></div>`;
  }
  function rowHtml(B, r, blind, btns) {
    const attrs = [];
    if (blind) attrs.push('data-stratum="" data-tier="" data-prov=""');
    else {
      const a = { stratum: r.stratum, tier: r.tier, prov: r.prov, simile: r.simile ? 1 : 0, veh: r.veh, vehcode: r.veh_code, rank: r.rank,
        vehb: r.veh_b, vehcodeb: r.veh_code_b, codeagree: r.code_agree, catagree: r.cat_agree, vehmain: r.veh_main, vehmainb: r.veh_main_b, mainagree: r.main_agree };
      for (const k in a) attrs.push(`data-${k}="${esc(a[k] == null ? '' : a[k])}"`);
      const ly = r.layers || {};
      for (const k of ['head', 'wn1', 'wn2', 'fn', 'llm', 'llm_c1', 'llm_c2']) attrs.push(`data-${k}="${esc(ly[k] || '')}"`);
    }
    attrs.push(`data-members="${esc(JSON.stringify(r.members || []))}" data-id="${esc(r.id)}"`);
    let meta;
    if (blind) meta = B.stage === 'filter' ? `<div class="meta"><span class="rank">${r.no} / ${B.rows.length}</span></div>` : '<div class="meta"></div>';
    else {
      const provpill = r.prov === 'plant' ? `<span class="pill plant">${esc(t('pill_plant'))}</span>`
        : r.prov === 'both' ? `<span class="pill old">${esc(t('pill_both', { old: B.old_label || '' }))}</span>` : `<span class="pill new">${esc(t('pill_new'))}</span>`;
      meta = `<div class="meta"><span class="rank">#${r.rank}</span><span class="pill s${r.tier}">${esc(t('tier_' + r.tier))}</span><span class="pill">${esc(t('pill_score', { s: Math.round(r.score) }))}</span>`
        + `<span class="pill">${esc(r.vivid ? t('pill_vivid') : t('pill_conventional'))}</span><span class="pill src">${esc(r.stratum)}</span>${provpill}`
        + (r.simile ? `<span class="pill sim">${esc(t('pill_simile'))}</span>` : '')
        + (r.veh ? `<span class="pill veh">${esc(r.veh_label || r.veh)}${r.veh_desc ? ' &middot; ' + esc(r.veh_desc) : ''}</span>` : '') + '</div>';
    }
    const n = r.n_pass || 1, vars = r.variants || [];
    const cnt = (r.members && r.members.length) ? `<span class="pill cnt" title="${esc(t('x_passages_title', { n }))}">&times;${esc(t('passages_n', { n }))}</span>` : '';
    const nv = r.n_variants || vars.length;
    const more = nv > 12 ? `<p class="ctx"><em>${esc(t('more_passages', { n: nv - 12 }))}</em></p>` : '';
    return `<div class="row" ${attrs.join(' ')}>${meta}<div class="phrase">${esc(r.phrase)}${cnt}</div>`
      + `<details><summary>${esc(t('context'))}${(r.members && r.members.length) ? ' · ' + esc(t('passages_n', { n })) : ''}</summary><p class="ctx">${highlight(r.text || '', r.phrase)}</p>`
      + vars.slice(0, 12).map(v => `<p class="ctx">${highlight(v.text || '', v.phrase || r.phrase)}</p>`).join('') + more + '</details>'
      + `<div class="lbl" data-for="${esc(r.id)}">` + VERDICTS.map((v, i) => `<button data-v="${v}">${esc(btns[i])}</button>`).join('') + '</div></div>';
  }

  // ------------------------------------------------------------------------ render ---
  function render(B) {
    setLang(B.lang);
    const blind = B.stage !== 'explore';
    document.body.className = blind ? 'review-page' : 'ranked-page';
    document.title = B.corpus + ' — ' + t('mode_' + B.stage);
    const btns = t('btn_' + B.stage);
    const h = [header(B, blind), projectContext(), stageStrip(B.stage)];
    if (!blind) { h.push(hero(B)); if (B.dataset_strip_html) h.push(B.dataset_strip_html); h.push(rankLogic(B)); }
    h.push(`<h1>${esc(B.corpus)} — ${esc(t('mode_' + B.stage))}</h1>`, statusBlock(B));
    if (!blind) h.push(vehSection(B));
    h.push(howBox(B), raterBox(B));
    if (!blind) h.push(behaved(B), plantBlock(B), provBlock(B), byStratum(B), scoreNote(B));
    h.push(`<div class="note">${B.private ? t('data_private') : t('data_public')}</div>`);
    h.push(!blind ? `<h2 id="candidates">${esc(t('cand_heading_ranked'))}</h2><p class="lede">${esc(t('cand_lede_ranked'))}</p>` : `<h2 id="candidates">${esc(t('cand_heading'))}</h2>`);
    if (!blind) h.push(`<div class="legend"><span class="pill plant">${esc(t('legend_plant'))}</span><span class="pill s0">${esc(t('legend_s0'))}</span><span class="pill s1">${esc(t('legend_s1'))}</span><span class="pill s2">${esc(t('legend_s2'))}</span><span class="pill new">${esc(t('legend_new'))}</span><span class="pill old">${esc(t('legend_old'))}</span></div>`);
    h.push(bar(B, blind), '<div id="returnbox" hidden></div>');   // confirmation sits right under the sticky bar with the export button
    h.push(B.rows.map(r => rowHtml(B, r, blind, btns)).join(''));
    h.push('<textarea id="out"></textarea>', siteFooter());
    document.getElementById('app').innerHTML = h.join('\n');
    behaviour(B, blind);
    const rl = document.getElementById('reload'); if (rl) rl.onclick = () => renderLoader(LANG, false);
  }

  // --------------------------------------------------------------------- behaviour ---
  function behaviour(B, blind) {
    const KEY = 'labels::' + (B.corpus_key || B.corpus) + (B.stage !== 'filter' ? '::' + B.stage : '') + (B.stream ? '::' + B.stream : '');
    let L = {};
    try { L = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) { L = {}; }
    const $ = id => document.getElementById(id);
    const rn = $('rname'), rr = $('rrole');
    try { rn.value = localStorage.getItem(KEY + '::name') || ''; const rv = localStorage.getItem(KEY + '::role'); if (rv) rr.value = rv; } catch (e) { }
    function saveRater() {
      try { localStorage.setItem(KEY + '::name', rn.value); localStorage.setItem(KEY + '::role', rr.value); } catch (e) { }
      $('rstate').textContent = (rn.value && rr.value) ? t('rater_saved') : t('rater_needed');
    }
    rn.oninput = saveRater; rr.onchange = saveRater; saveRater();

    const rows = [...document.querySelectorAll('.row')];
    function paint(r) {
      const v = L[r.dataset.id];
      r.classList.toggle('done', !!v);
      r.querySelectorAll('.lbl button').forEach(b => b.classList.toggle('sel', b.dataset.v === v));
    }
    document.querySelectorAll('.lbl').forEach(g => g.addEventListener('click', ev => {
      const b = ev.target.closest('button'); if (!b) return;
      const id = g.dataset.for;
      if (L[id] === b.dataset.v) delete L[id]; else L[id] = b.dataset.v;
      try { localStorage.setItem(KEY, JSON.stringify(L)); } catch (e) { }
      paint(g.closest('.row')); apply();
    }));

    let GX = [];
    const val = id => ($(id) || { value: '' }).value;
    function apply() {
      const s = val('fs'), tt = val('ft'), p = val('fp'), l = val('fl'), mk = val('fm'), vh = val('fv'), vc = val('fc'), q = val('fq').trim().toLowerCase();
      let n = 0;
      for (const r of rows) {
        const v = L[r.dataset.id];
        const ok = (!s || r.dataset.stratum === s) && (!tt || r.dataset.tier === tt) && (!p || r.dataset.prov === p)
          && (!mk || r.dataset.simile === mk) && (!vh || r.dataset.veh === vh) && (!vc || r.dataset.vehcode === vc)
          && (!q || r.textContent.toLowerCase().includes(q))
          && GX.every(g => (r.dataset[g.layer] || t('veh_nolabel')) === g.val)
          && (!l || (l === 'todo' ? !v : v === l));
        r.style.display = ok ? '' : 'none'; if (ok) n++;
      }
      $('count').textContent = t('count', { n, k: rows.filter(r => L[r.dataset.id]).length }) + (GX.length ? t('count_filter', { f: gxLabel() }) : '');
    }
    ['fs', 'ft', 'fp', 'fl', 'fm', 'fv', 'fc'].forEach(i => { const el = $(i); if (el) el.onchange = apply; });
    { const fq = $('fq'); if (fq) fq.oninput = apply; }

    // ---- source-domain table (explore only) ----
    const CODE_DESC = B.code_desc || {};
    const CODE_LAYERS = new Set(['vehcode', 'vehcodeb', 'codeagree', 'vehmain', 'vehmainb', 'mainagree']);
    const USAS_LAYERS = new Set(['veh', 'vehmain', 'vehcode']);
    const BASE = { vehb: 'veh', vehmainb: 'vehmain', vehcodeb: 'vehcode', catagree: 'veh', mainagree: 'vehmain', codeagree: 'vehcode' };
    const SHOW_SUB = 8, OPEN = new Set();
    function famKey(layer) {
      if (!USAS_LAYERS.has(layer)) return layer;
      const f = ($('vfam') || { value: 'a' }).value;
      if (f === 'b') return layer + 'b';
      if (f === 'agree') return { veh: 'catagree', vehmain: 'mainagree', vehcode: 'codeagree' }[layer];
      return layer;
    }
    function famName() { const el = $('vfam'); if (!el) return ''; return ' (' + el.options[el.selectedIndex].text.replace(/ \(.*\)$/, '') + ')'; }
    function levelName(k) { return t('ln_' + (BASE[k] || k)); }
    function gxLabel() { return GX.map(g => levelName(g.layer) + ' = ' + g.val).join(' › '); }
    function show(layer, v) {
      if (!CODE_LAYERS.has(layer)) return esc(v);
      const d = CODE_DESC[v] || CODE_DESC[v.replace(/[+-]+$/, '')] || '';
      return esc(v) + (d ? ' <span style="color:var(--mut);font-weight:400"> — ' + esc(d) + (/[+-]$/.test(v) ? ' (' + (v.endsWith('+') ? t('pole_pos') : t('pole_neg')) + ')' : '') + '</span>' : '');
    }
    function levelsFor() {
      const g1 = val('vlayer'), g2 = val('vlayer2');
      const lv = g1 === 'usas' ? ['vehmain', 'vehcode'] : [g1];
      if (g2 && g2 !== g1) lv.push(g2);
      return lv.map(famKey);
    }
    function group(list, key) {
      const m = new Map();
      for (const r of list) { const v = r.dataset[key] || t('veh_nolabel'); if (!m.has(v)) m.set(v, []); m.get(v).push(r); }
      return [...m.entries()].sort((a, b) => b[1].length - a[1].length);
    }
    function pathOn(path) { return path.length === GX.length && path.every((g, i) => GX[i].layer === g.layer && GX[i].val === g.val); }
    function buildVeh() {
      const tab = $('vtab'); if (!tab) return;
      const LV = levelsFor();
      const X = parseInt(val('vtop')) || rows.length;
      const inTop = rows.filter(r => { const rk = parseInt(r.dataset.rank); return rk && rk <= X; });
      const labelled = inTop.filter(r => r.dataset[LV[0]]);
      const max = Math.max(1, ...group(labelled, LV[0]).map(([, l]) => l.length));
      let h = '<tr><th>' + LV.map(levelName).join(' › ') + (USAS_LAYERS.has(BASE[LV[0]] || LV[0]) ? famName() : '') + '</th><th>n</th><th>%</th><th></th></tr>';
      let distinct = 0;
      const render = (list, depth, path, parentN, parentLabel) => {
        const key = LV[depth];
        const items = group(list, key);
        if (depth > 0 && items.length === 1 && items[0][0] === path[path.length - 1].val)
          return depth + 1 < LV.length ? render(list, depth + 1, path, parentN, parentLabel) : '';
        if (depth === 0) distinct = items.length;
        const okey = path.map(g => g.val).join('␟');
        const lim = (depth === 0 || OPEN.has(okey)) ? items.length : SHOW_SUB;
        let out = '';
        items.slice(0, lim).forEach(([v, l]) => {
          if (depth === 0 && v === t('veh_nolabel')) return;
          const p = path.concat([{ layer: key, val: v }]);
          const share = depth === 0 ? (100 * l.length / labelled.length).toFixed(1) + '%' : (100 * l.length / parentN).toFixed(0) + t('veh_of_parent') + esc(parentLabel);
          out += '<tr class="' + (depth === 0 ? 'grp' : 'sub') + (pathOn(p) ? ' on' : '') + '" data-path="' + esc(JSON.stringify(p)) + '"><td style="padding-left:' + (depth * 22 + 8) + 'px">' + show(key, v)
            + '</td><td>' + l.length + '</td><td>' + share + '</td><td><span class="bar" style="width:' + Math.round(160 * l.length / max) + 'px;opacity:' + (depth ? .3 : .55) + '"></span></td></tr>';
          if (depth + 1 < LV.length) out += render(l, depth + 1, p, l.length, v);
        });
        if (items.length > lim) out += '<tr class="more" data-open="' + esc(okey) + '"><td colspan="4" style="padding-left:' + (depth * 22 + 8) + 'px">' + esc(t('veh_more', { n: items.length - lim })) + '</td></tr>';
        else if (depth > 0 && OPEN.has(okey) && items.length > SHOW_SUB) out += '<tr class="more" data-close="' + esc(okey) + '"><td colspan="4" style="padding-left:' + (depth * 22 + 8) + 'px">' + esc(t('veh_fewer')) + '</td></tr>';
        return out;
      };
      h += render(labelled, 0, [], labelled.length, '');
      tab.innerHTML = h;
      $('vcov').textContent = t('veh_cov', { k: labelled.length, n: inTop.length, d: distinct });
      const vcl = $('vclear');
      vcl.className = GX.length ? 'show' : ''; vcl.textContent = GX.length ? t('veh_clear_with', { f: gxLabel() }) : t('veh_clear');
      const go = () => { buildVeh(); apply(); $('bar').scrollIntoView({ behavior: 'smooth' }); };
      tab.querySelectorAll('tr[data-path]').forEach(tr => tr.onclick = () => {
        const p = JSON.parse(tr.dataset.path); GX = pathOn(p) ? [] : p;
        ['fv', 'fc'].forEach(i => { const el = $(i); if (el) el.value = ''; }); go(); });
      tab.querySelectorAll('tr.more').forEach(tr => tr.onclick = () => {
        if (tr.dataset.open !== undefined) OPEN.add(tr.dataset.open); else OPEN.delete(tr.dataset.close); buildVeh(); });
    }
    { const vcl = $('vclear'); if (vcl) vcl.onclick = () => { GX = []; buildVeh(); apply(); }; }
    { const vl = $('vlayer'), vl2 = $('vlayer2'), vt = $('vtop'), vf = $('vfam');
      if (vf) vf.onchange = () => { GX = []; OPEN.clear(); buildVeh(); apply(); };
      if (vl) { vl.onchange = vl2.onchange = () => { GX = []; OPEN.clear(); buildVeh(); apply(); }; vt.oninput = buildVeh; buildVeh(); } }
    $('fr').onclick = () => {
      ['fs', 'ft', 'fp', 'fl', 'fm', 'fv', 'fc', 'fq'].forEach(i => { const el = $(i); if (el) el.value = ''; });
      GX = []; buildVeh(); apply(); };

    // ---- export + return flow ----
    $('ex').onclick = () => {
      if (!rn.value || !rr.value) { alert(t('export_need')); return; }
      const ALL = {};
      for (const r of rows) {
        const v = L[r.dataset.id]; if (!v) continue;
        ALL[r.dataset.id] = v;
        try { for (const m of JSON.parse(r.dataset.members || '[]')) ALL[m] = v; } catch (e) { }
      }
      const blob = JSON.stringify({ corpus: B.corpus_key || B.corpus, list: B.list_id || '', lang: B.lang, stage: B.stage, stream: B.stream || '',
        rater: { name: rn.value, role: rr.value }, n_labelled: rows.filter(r => L[r.dataset.id]).length, n_candidate_ids: Object.keys(ALL).length, labels: ALL }, null, 1);
      const fname = 'labels_' + rn.value.replace(/\W+/g, '_') + '_' + rr.value + (B.list_id ? '_' + B.list_id : '') + '.json';
      const ta = $('out'); ta.style.display = 'block'; ta.value = blob;
      const rb0 = $('returnbox'); rb0.hidden = false;
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([blob], { type: 'application/json' })); a.download = fname; a.click();
      const to = B.return_to || '';
      const subject = t('return_subject', { corpus: B.corpus, name: rn.value });
      const body = t('return_body', { file: fname, corpus: B.corpus, stage: t('mode_' + B.stage), name: rn.value });
      const rb = $('returnbox');
      rb.innerHTML = `<div class="status returnbox"><div class="l1"><b>${esc(t('return_heading'))}</b></div><div class="l2">${to ? t('return_text', { file: esc(fname), to: esc(to) }) : t('return_text_noaddr', { file: esc(fname) })}</div>`
        + (to ? `<div class="l3"><a class="button primary" href="mailto:${encodeURIComponent(to)}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}">${esc(t('return_mail', { to }))}</a></div>` : '')
        + `<div class="l3">${esc(t('return_copy'))}</div></div>`;
      rb.hidden = false; rb.scrollIntoView({ behavior: 'smooth' });
    };
    const lt = $('labelToggle');
    if (lt) {
      const setLabelling = on => { document.body.classList.toggle('labelling', on); lt.setAttribute('aria-pressed', String(on)); lt.textContent = on ? t('hero_label_off') : t('hero_label_on'); };
      lt.onclick = () => setLabelling(!document.body.classList.contains('labelling'));
      setLabelling(Object.keys(L).length > 0);
    }
    rows.forEach(paint); apply();
  }

  // -------------------------------------------------------------------------- boot ---
  const emb = document.getElementById('bundle');
  if (emb && emb.textContent.trim()) {
    try { render(JSON.parse(emb.textContent)); } catch (e) { console.error(e); renderLoader(browserLang(), true); }
  } else renderLoader(browserLang(), false);
  window.__review = { render, renderLoader, loadFile, decryptBundle };
})();
