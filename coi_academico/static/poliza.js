(function () {
  const tbody = document.querySelector('#movs tbody');
  const tpl = document.getElementById('fila');
  if (!tbody || !tpl) return;
  const fmt = n => n.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
  function totales() {
    let d = 0, h = 0;
    tbody.querySelectorAll('input[name=debe]').forEach(i => d += parseFloat(i.value) || 0);
    tbody.querySelectorAll('input[name=haber]').forEach(i => h += parseFloat(i.value) || 0);
    document.getElementById('td').textContent = fmt(d);
    document.getElementById('th').textContent = fmt(h);
    const dif = Math.round((d - h) * 100) / 100;
    const el = document.getElementById('dif');
    el.textContent = dif === 0 ? 'Póliza cuadrada ✓' : 'Diferencia: ' + fmt(dif);
    el.style.color = dif === 0 ? '#1b7f3b' : '#b3261e';
  }
  function agregar() {
    tbody.appendChild(tpl.content.cloneNode(true));
    totales();
  }
  document.getElementById('agregar').addEventListener('click', agregar);
  tbody.addEventListener('input', totales);
  tbody.addEventListener('click', e => {
    if (e.target.classList.contains('quitar') && tbody.rows.length > 2) {
      e.target.closest('tr').remove();
      totales();
    }
  });
  agregar(); agregar();
})();
