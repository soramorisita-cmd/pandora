// PANDORA click tracker
// 商品カードの「Kakobuyで見る」ボタンと「QC」ボタンをクリック時に /api/click を叩く
// 連続クリックの抑止と localStorage 重複防止付き
(function(){
  const LS_KEY = 'pdra_clicks_v1';
  const THROTTLE_MS = 1500; // 同一商品の連続クリック抑制
  let recent = {};
  try { recent = JSON.parse(localStorage.getItem(LS_KEY) || '{}'); } catch {}

  function extractYupooId(href){
    if(!href) return '';
    const m = href.match(/\/albums\/(\d+)/);
    return m ? m[1] : '';
  }

  function track(yupooId, kind){
    if(!yupooId) return;
    const now = Date.now();
    const key = yupooId + ':' + kind;
    if(recent[key] && (now - recent[key]) < THROTTLE_MS) return;
    recent[key] = now;
    // 100件超で古いものを削除
    const entries = Object.entries(recent);
    if(entries.length > 100){
      entries.sort((a,b) => a[1] - b[1]);
      recent = Object.fromEntries(entries.slice(-80));
    }
    try { localStorage.setItem(LS_KEY, JSON.stringify(recent)); } catch {}

    fetch('/api/click', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ yupoo_id: yupooId, kind: kind }),
      keepalive: true,
    }).catch(()=>{}); // エラーは無視
  }

  document.addEventListener('click', function(e){
    const btn = e.target.closest('.btn-buy, .btn-qc');
    if(!btn) return;
    // QCボタンは yupoo URL（自分のサイトの album）
    // 買うボタンは kakobuy URL（その中にyupoo情報なし）→ 同カードの QC リンクから取る
    const card = btn.closest('.card');
    let yupooHref = '';
    if(card){
      const qcLink = card.querySelector('.btn-qc');
      if(qcLink) yupooHref = qcLink.href;
    }
    const yupooId = extractYupooId(yupooHref) || extractYupooId(btn.href);
    const kind = btn.classList.contains('btn-qc') ? 'qc' : 'buy';
    track(yupooId, kind);
  }, true);
})();
