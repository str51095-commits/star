(function () {
  var form = document.getElementById('planform');
  if (!form) return;
  var $ = function (n) { return form.elements[n]; };
  var D = window.PV_DEFAULTS || {};

  function show(sel, on) {
    form.querySelectorAll(sel).forEach(function (el) { el.style.display = on ? '' : 'none'; });
  }
  function toggle() {
    var t = $('project_type').value, g = $('grid_mode').value, m = $('model').value;
    show('.only-ci', t === '工商业');
    show('.only-home', t !== '工商业');
    show('.g-ratio', g === '自发自用，余电上网');
    ['emc', 'self', 'rent'].forEach(function (k) { show('.m-' + k, false); });
    show('.m-' + m, true);
    show('.g-grid', m === 'emc' || g !== '全额上网');
    if (m === 'self') show('.g-feed', g !== '全部自发自用');
  }

  // 切换项目类型时，没改过的字段换成对应类型的默认值
  var lastType = $('project_type').value;
  $('project_type').addEventListener('change', function () {
    var from = D[lastType] || {}, to = D[this.value] || {};
    Object.keys(to).forEach(function (k) {
      var el = $(k);
      if (!el || k === 'project_type') return;
      if (el.value === '' || el.value === (from[k] || '')) el.value = to[k];
    });
    lastType = this.value;
    toggle(); preview();
  });

  var timer = null, seq = 0;
  function preview() {
    clearTimeout(timer);
    timer = setTimeout(function () {
      var my = ++seq;
      fetch('/api/preview', { method: 'POST', body: new FormData(form), headers: { 'X-CSRF': $('_csrf').value } })
        .then(function (r) { return r.json(); })
        .then(function (j) {
          if (my !== seq) return;
          var out = document.getElementById('pv-out');
          if (!j.ok) { out.className = 'muted'; out.textContent = j.error; return; }
          out.className = '';
          out.innerHTML = '<table class="kv">' + j.items.map(function (it) {
            return '<tr><th>' + esc(it[0]) + '</th><td>' + esc(it[1]) + '</td></tr>';
          }).join('') + '</table>';
        }).catch(function () {});
    }, 400);
  }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }

  form.addEventListener('input', preview);
  form.addEventListener('change', function () { toggle(); preview(); });
  form.addEventListener('submit', function () {
    var b = form.querySelector('button[type=submit]');
    b.disabled = true; b.textContent = '正在生成，请稍候…';
  });
  toggle(); preview();
})();
