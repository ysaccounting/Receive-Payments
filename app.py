import io
import os
import json
import zipfile
import threading
import uuid
import tempfile
from flask import Flask, request, jsonify, send_file
from processor import process_file, process_files

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50MB

JOBS_DIR = os.path.join(tempfile.gettempdir(), "ysledger_jobs")
os.makedirs(JOBS_DIR, exist_ok=True)

FILE_PREFIX = "Receive Payments"


def job_dir(job_id):
    return os.path.join(JOBS_DIR, job_id)


def write_job_status(job_id, status, message=None):
    d = job_dir(job_id)
    os.makedirs(d, exist_ok=True)
    payload = {"status": status}
    if message:
        payload["message"] = message
    with open(os.path.join(d, "status.json"), "w") as f:
        json.dump(payload, f)


def read_job_status(job_id):
    path = os.path.join(job_dir(job_id), "status.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def read_meta(job_id):
    path = os.path.join(job_dir(job_id), "meta.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def run_job(job_id, file_list):
    try:
        result = process_files(file_list)
        d = job_dir(job_id)

        with open(os.path.join(d, "combined.xlsx"), "wb") as f:
            f.write(result["combined"])

        companies_dir = os.path.join(d, "companies")
        os.makedirs(companies_dir, exist_ok=True)
        for company, data in result["companies"].items():
            safe = company.replace("/", "_").replace("\\", "_")
            with open(os.path.join(companies_dir, f"{safe}.xlsx"), "wb") as f:
                f.write(data)

        meta = {
            "date_range": result["date_range"],
            "companies": list(result["companies"].keys()),
            "all_companies": result.get("all_companies", list(result["companies"].keys())),
            "stats": result.get("stats", {}),
        }
        with open(os.path.join(d, "meta.json"), "w") as f:
            json.dump(meta, f)

        write_job_status(job_id, "done")

    except Exception as e:
        write_job_status(job_id, "error", str(e))


@app.route("/")
def index():
    return INDEX_HTML


@app.route("/upload", methods=["POST"])
def upload():
    files = request.files.getlist("file")
    if not files or all(f.filename == "" for f in files):
        return jsonify({"error": "No files provided"}), 400
    file_list = [(f.read(), f.filename) for f in files if f.filename]
    job_id = str(uuid.uuid4())
    write_job_status(job_id, "processing")
    threading.Thread(target=run_job, args=(job_id, file_list), daemon=True).start()
    return jsonify({"job_id": job_id})


@app.route("/status/<job_id>")
def status(job_id):
    job = read_job_status(job_id)
    if not job:
        return jsonify({"status": "not_found"}), 404
    if job["status"] in ("error", "processing"):
        return jsonify(job)
    meta = read_meta(job_id)
    if not meta:
        return jsonify({"status": "error", "message": "Result files missing"}), 500
    return jsonify({
        "status": "done",
        "date_range": meta["date_range"],
        "companies": meta["companies"],
        "all_companies": meta.get("all_companies", meta["companies"]),
        "stats": meta.get("stats", {}),
    })


@app.route("/download/<job_id>/combined")
def download_combined(job_id):
    meta = read_meta(job_id)
    if not meta:
        return jsonify({"error": "Job not found"}), 404
    path = os.path.join(job_dir(job_id), "combined.xlsx")
    if not os.path.exists(path):
        return jsonify({"error": "File not found"}), 404
    return send_file(path, as_attachment=True,
                     download_name=f"{FILE_PREFIX} - Combined - {meta['date_range']}.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/download/<job_id>/company/<company>")
def download_company(job_id, company):
    meta = read_meta(job_id)
    if not meta:
        return jsonify({"error": "Job not found"}), 404
    safe = company.replace("/", "_").replace("\\", "_")
    path = os.path.join(job_dir(job_id), "companies", f"{safe}.xlsx")
    if not os.path.exists(path):
        return jsonify({"error": "File not found"}), 404
    return send_file(path, as_attachment=True,
                     download_name=f"{FILE_PREFIX} - {company} - {meta['date_range']}.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/download/<job_id>/all")
def download_all_zip(job_id):
    meta = read_meta(job_id)
    if not meta:
        return jsonify({"error": "Job not found"}), 404
    d = job_dir(job_id)
    dr = meta["date_range"]
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        combined = os.path.join(d, "combined.xlsx")
        if os.path.exists(combined):
            zf.write(combined, f"{FILE_PREFIX} - Combined - {dr}.xlsx")
        for company in meta["companies"]:
            safe = company.replace("/", "_").replace("\\", "_")
            cp = os.path.join(d, "companies", f"{safe}.xlsx")
            if os.path.exists(cp):
                zf.write(cp, f"{FILE_PREFIX} - {company} - {dr}.xlsx")
    zip_buf.seek(0)
    return send_file(zip_buf, mimetype="application/zip", as_attachment=True,
                     download_name=f"{FILE_PREFIX} - {dr}.zip")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)


INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Receive Payments — Y&amp;S Ledger</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600;9..144,900&family=Spline+Sans+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root{
    --paper:#f4f0e6; --ink:#1c1a17; --ink-soft:#5b554a;
    --line:#d8d1bf; --accent:#1d6b4f; --accent-soft:#e3ede7;
    --red:#a8341f; --card:#fbf9f3;
    --shadow:0 1px 0 rgba(28,26,23,.04),0 18px 40px -28px rgba(28,26,23,.45);
  }
  *{box-sizing:border-box}
  html,body{margin:0}
  body{
    font-family:"Spline Sans Mono",monospace;
    background:var(--paper);
    color:var(--ink);
    line-height:1.5;
    background-image:radial-gradient(circle at 1px 1px,rgba(28,26,23,.05) 1px,transparent 0);
    background-size:22px 22px;
    min-height:100vh;
  }
  .wrap{max-width:920px;margin:0 auto;padding:56px 24px 80px}
  header{border-bottom:2px solid var(--ink);padding-bottom:20px;margin-bottom:40px}
  .eyebrow{font-size:12px;letter-spacing:.32em;text-transform:uppercase;color:var(--ink-soft)}
  h1{font-family:"Fraunces",serif;font-weight:900;font-size:clamp(38px,7vw,68px);
     line-height:.95;margin:10px 0 0;letter-spacing:-.02em}
  h1 em{font-style:italic;color:var(--accent)}
  .sub{margin-top:14px;color:var(--ink-soft);max-width:60ch;font-size:14px}

  .drop{
    border:2px dashed var(--line);border-radius:14px;background:var(--card);
    padding:46px 28px;text-align:center;cursor:pointer;transition:.18s ease;
    box-shadow:var(--shadow);
  }
  .drop:hover,.drop.over{border-color:var(--accent);background:var(--accent-soft);transform:translateY(-1px)}
  .drop .big{font-family:"Fraunces",serif;font-size:24px;font-weight:600}
  .drop .small{color:var(--ink-soft);font-size:13px;margin-top:6px}
  .drop svg{width:34px;height:34px;color:var(--accent);margin-bottom:8px}
  input[type=file]{display:none}

  .filelist{margin:16px 0 0;display:flex;flex-direction:column;gap:6px}
  .filerow{display:flex;justify-content:space-between;align-items:center;
    background:var(--card);border:1px solid var(--line);border-radius:8px;
    padding:8px 14px;font-size:13px}
  .filerow span:last-child{color:var(--ink-soft)}

  button{font-family:inherit;cursor:pointer;border:none}
  .go{
    margin-top:18px;width:100%;background:var(--ink);color:var(--paper);
    font-size:15px;font-weight:500;padding:16px;border-radius:10px;letter-spacing:.02em;
    transition:.15s ease;
  }
  .go:hover:not(:disabled){background:var(--accent)}
  .go:disabled{opacity:.4;cursor:not-allowed}

  .panel{margin-top:34px;display:none}
  .panel.show{display:block;animation:rise .4s ease both}
  @keyframes rise{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}

  .status{display:flex;align-items:center;gap:12px;font-size:14px;color:var(--ink-soft)}
  .spinner{width:18px;height:18px;border:2px solid var(--line);border-top-color:var(--accent);
    border-radius:50%;animation:spin .8s linear infinite}
  @keyframes spin{to{transform:rotate(360deg)}}

  .daterange{font-family:"Fraunces",serif;font-style:italic;font-size:20px;color:var(--ink);margin:2px 0 22px}
  .toolbar{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:22px}
  .btn{padding:11px 18px;border-radius:9px;font-size:13px;font-weight:500;text-decoration:none;
    display:inline-flex;align-items:center;gap:8px;border:1px solid var(--ink);color:var(--ink);background:transparent;transition:.15s}
  .btn:hover{background:var(--ink);color:var(--paper)}
  .btn.primary{background:var(--accent);border-color:var(--accent);color:#fff}
  .btn.primary:hover{background:#155138}

  table{width:100%;border-collapse:collapse;font-size:13px;background:var(--card);
    border:1px solid var(--line);border-radius:12px;overflow:hidden}
  th,td{text-align:left;padding:11px 16px;border-bottom:1px solid var(--line)}
  th{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--ink-soft);font-weight:600}
  tbody tr:last-child td{border-bottom:none}
  tbody tr.empty td{color:#b3aa96}
  td.num{text-align:right;font-variant-numeric:tabular-nums}
  td .dl{color:var(--accent);text-decoration:none;font-weight:500}
  td .dl:hover{text-decoration:underline}
  .pill{font-size:11px;padding:2px 8px;border-radius:20px;background:var(--accent-soft);color:var(--accent)}
  .pill.zero{background:#f0e6e2;color:var(--red)}

  .err{background:#f6e3de;border:1px solid var(--red);color:var(--red);
    padding:14px 18px;border-radius:10px;font-size:13px;margin-top:20px}
  footer{margin-top:48px;font-size:12px;color:var(--ink-soft);border-top:1px solid var(--line);padding-top:16px}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="eyebrow">Y&amp;S Affiliates · Bookkeeping</div>
    <h1>Receive <em>Payments</em></h1>
    <p class="sub">Drop one or more ledger exports. Get a combined workbook with a tab per company, plus an individual file for each company — matching the workbook's Power Query logic.</p>
  </header>

  <div id="drop" class="drop">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M12 16V4m0 0L8 8m4-4l4 4" stroke-linecap="round" stroke-linejoin="round"/><path d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2" stroke-linecap="round"/></svg>
    <div class="big">Drop ledger files here</div>
    <div class="small">or click to browse · .xlsx, .xlsm, .csv · multiple allowed</div>
  </div>
  <input type="file" id="fileInput" multiple accept=".xlsx,.xlsm,.csv">
  <div id="filelist" class="filelist"></div>
  <button id="go" class="go" disabled>Process ledger</button>

  <div id="errBox"></div>

  <section id="panel" class="panel">
    <div id="status" class="status"><div class="spinner"></div><span>Processing…</span></div>
    <div id="results" style="display:none">
      <div class="daterange" id="daterange"></div>
      <div class="toolbar">
        <a id="dlCombined" class="btn primary" href="#">↧ Combined workbook</a>
        <a id="dlZip" class="btn" href="#">↧ All files (.zip)</a>
      </div>
      <table>
        <thead><tr><th>Company</th><th>Rows</th><th class="num">Amount Received</th><th>File</th></tr></thead>
        <tbody id="rows"></tbody>
      </table>
    </div>
  </section>

  <footer>Built to mirror the Receive Payments (Y&amp;S Ledger) Power Query · runs on Railway</footer>
</div>

<script>
const drop=document.getElementById('drop'),input=document.getElementById('fileInput'),
      filelist=document.getElementById('filelist'),go=document.getElementById('go'),
      panel=document.getElementById('panel'),statusEl=document.getElementById('status'),
      results=document.getElementById('results'),rowsEl=document.getElementById('rows'),
      errBox=document.getElementById('errBox');
let files=[];

const money=n=>'$'+Number(n||0).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});

function render(){
  filelist.innerHTML=files.map(f=>`<div class="filerow"><span>${f.name}</span><span>${(f.size/1024).toFixed(0)} KB</span></div>`).join('');
  go.disabled=files.length===0;
}
drop.onclick=()=>input.click();
input.onchange=e=>{files=[...e.target.files];render()};
['dragover','dragenter'].forEach(ev=>drop.addEventListener(ev,e=>{e.preventDefault();drop.classList.add('over')}));
['dragleave','drop'].forEach(ev=>drop.addEventListener(ev,e=>{e.preventDefault();drop.classList.remove('over')}));
drop.addEventListener('drop',e=>{files=[...e.dataTransfer.files];render()});

go.onclick=async()=>{
  errBox.innerHTML='';go.disabled=true;panel.classList.add('show');
  results.style.display='none';statusEl.style.display='flex';
  const fd=new FormData();files.forEach(f=>fd.append('file',f));
  try{
    const r=await fetch('/upload',{method:'POST',body:fd});
    const j=await r.json();
    if(!r.ok){throw new Error(j.error||'Upload failed')}
    poll(j.job_id);
  }catch(e){fail(e.message);go.disabled=false}
};

function fail(msg){
  statusEl.style.display='none';
  errBox.innerHTML=`<div class="err">⚠ ${msg}</div>`;
}

async function poll(id){
  try{
    const r=await fetch('/status/'+id);const j=await r.json();
    if(j.status==='processing'){return setTimeout(()=>poll(id),900)}
    if(j.status==='error'){fail(j.message||'Processing error');go.disabled=false;return}
    done(id,j);
  }catch(e){setTimeout(()=>poll(id),1200)}
}

function done(id,j){
  statusEl.style.display='none';results.style.display='block';go.disabled=false;
  document.getElementById('daterange').textContent=j.date_range;
  document.getElementById('dlCombined').href=`/download/${id}/combined`;
  document.getElementById('dlZip').href=`/download/${id}/all`;
  const withFiles=new Set(j.companies);
  const stats=j.stats||{};
  rowsEl.innerHTML=j.all_companies.map(c=>{
    const s=stats[c]||{rows:0,total:0};
    const has=withFiles.has(c);
    return `<tr class="${has?'':'empty'}">
      <td>${c}</td>
      <td><span class="pill ${s.rows?'':'zero'}">${s.rows}</span></td>
      <td class="num">${money(s.total)}</td>
      <td>${has?`<a class="dl" href="/download/${id}/company/${encodeURIComponent(c)}">↧ download</a>`:'—'}</td>
    </tr>`;
  }).join('');
}
</script>
</body>
</html>
"""
