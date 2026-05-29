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

INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Receive Payments</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  :root{
    --bg:#f1f2f4; --card:#ffffff; --ink:#1e2433; --ink-soft:#6b7280;
    --line:#e6e8ee; --indigo:#6366f1; --indigo-dark:#5254e0; --indigo-soft:#eef0fb;
    --drop:#f7f8fa; --drop-line:#cdd0e8;
    --green:#16a085; --green-dark:#138a72; --green-mute:#b3d4ca; --green-soft:#e7f4f0;
    --red:#c0392b;
    --shadow:0 1px 2px rgba(30,36,51,.04), 0 24px 48px -28px rgba(30,36,51,.28);
  }
  *{box-sizing:border-box}
  html,body{margin:0}
  body{
    font-family:"Plus Jakarta Sans",system-ui,sans-serif;
    background:var(--bg); color:var(--ink); line-height:1.5;
    min-height:100vh; display:flex; align-items:flex-start; justify-content:center;
    padding:56px 20px 80px;
  }
  .card{
    width:100%; max-width:680px; background:var(--card);
    border-radius:18px; box-shadow:var(--shadow); padding:40px 40px 44px;
  }
  h1{font-size:28px; font-weight:800; letter-spacing:-.02em; margin:0}
  .sub{color:var(--ink-soft); font-size:14.5px; margin:10px 0 0; max-width:54ch}

  .drop{
    margin-top:28px; border:2px dashed var(--drop-line); border-radius:14px;
    background:var(--drop); padding:46px 28px; text-align:center; cursor:pointer;
    transition:.18s ease;
  }
  .drop:hover,.drop.over{border-color:var(--indigo); background:var(--indigo-soft)}
  .drop .ico{width:44px; height:44px; margin:0 auto 14px; color:var(--indigo)}
  .drop .ico svg{width:100%; height:100%}
  .drop .big{font-size:15px; color:var(--ink)}
  .drop .big b{font-weight:700}
  .drop .browse{color:var(--indigo); font-weight:600; text-decoration:underline; cursor:pointer}
  .drop .small{font-size:13px; color:var(--ink-soft); margin-top:6px}
  input[type=file]{display:none}

  .filelist{margin:16px 0 0; display:flex; flex-direction:column; gap:6px}
  .filerow{display:flex; justify-content:space-between; align-items:center;
    background:var(--drop); border:1px solid var(--line); border-radius:9px;
    padding:9px 14px; font-size:13px}
  .filerow span:last-child{color:var(--ink-soft)}

  button{font-family:inherit; cursor:pointer; border:none}
  .actions{display:flex; gap:10px; margin-top:18px}
  .go{
    flex:1; background:var(--indigo); color:#fff;
    font-size:15px; font-weight:600; padding:15px; border-radius:11px;
    transition:.15s ease; letter-spacing:.01em;
  }
  .go:hover:not(:disabled){background:var(--indigo-dark)}
  .go:disabled{opacity:.45; cursor:not-allowed}
  .clear{
    background:#fff; color:var(--ink-soft); border:1px solid var(--line);
    font-size:15px; font-weight:600; padding:15px 22px; border-radius:11px; transition:.15s ease;
  }
  .clear:hover{border-color:var(--indigo); color:var(--indigo)}

  .panel{margin-top:30px; display:none}
  .panel.show{display:block; animation:rise .4s ease both}
  @keyframes rise{from{opacity:0; transform:translateY(10px)}to{opacity:1; transform:none}}

  .status{display:flex; align-items:center; gap:12px; font-size:14px; color:var(--ink-soft)}
  .spinner{width:18px; height:18px; border:2px solid var(--line); border-top-color:var(--indigo);
    border-radius:50%; animation:spin .8s linear infinite}
  @keyframes spin{to{transform:rotate(360deg)}}

  .daterange{font-size:13px; color:var(--ink-soft); margin:0 0 16px}
  .daterange b{color:var(--ink); font-weight:700}

  .dlcard{display:flex; align-items:center; gap:14px; padding:14px 16px;
    border:1px solid var(--line); border-radius:12px; text-decoration:none;
    background:#fff; transition:.15s; margin-bottom:6px}
  .dlcard:hover{border-color:var(--green)}
  .dlcard-ico{width:38px; height:38px; border-radius:9px; background:var(--green);
    color:#fff; display:flex; align-items:center; justify-content:center; flex-shrink:0}
  .dlcard-ico svg{width:20px; height:20px}
  .dlcard-txt{display:flex; flex-direction:column}
  .dlcard-txt b{font-size:14.5px; color:var(--ink); font-weight:700}
  .dlcard-txt span{font-size:12.5px; color:var(--ink-soft)}

  .seclabel{font-size:11px; letter-spacing:.08em; text-transform:uppercase;
    color:var(--ink-soft); font-weight:600; margin:24px 0 12px}

  .summary{width:100%; border-collapse:collapse; font-size:13.5px;
    border:1px solid var(--line); border-radius:12px; overflow:hidden}
  .summary th{text-align:left; font-size:11px; letter-spacing:.07em; text-transform:uppercase;
    color:var(--ink-soft); font-weight:600; padding:10px 16px; border-bottom:1px solid var(--line)}
  .summary th.num, .summary td.num{text-align:right; font-variant-numeric:tabular-nums}
  .summary td{padding:11px 16px; border-bottom:1px solid var(--line); color:var(--ink)}
  .summary tbody tr:last-child td{border-bottom:none}
  .summary .combined-row{background:var(--indigo-soft)}
  .summary .combined-row td{font-weight:700}
  .summary tr.zero td{color:var(--ink-soft)}

  .filegrid{display:grid; grid-template-columns:1fr 1fr; gap:10px}
  .fcard{display:flex; align-items:center; gap:12px; padding:14px;
    border:1px solid var(--line); border-radius:12px; text-decoration:none; background:#fff; transition:.15s}
  .fcard.has:hover{border-color:var(--green)}
  .fcard-ico{width:34px; height:34px; border-radius:9px; display:flex;
    align-items:center; justify-content:center; flex-shrink:0}
  .fcard-ico svg{width:18px; height:18px}
  .fcard.has .fcard-ico{background:var(--green); color:#fff}
  .fcard.no .fcard-ico{background:var(--green-mute); color:#fff}
  .fcard-txt{display:flex; flex-direction:column}
  .fcard-name{font-size:14px; font-weight:600; color:var(--ink)}
  .fcard.no .fcard-name{color:var(--ink-soft)}
  .fcard-sub{font-size:12px; color:var(--ink-soft); font-weight:400}
  @media(max-width:520px){.filegrid{grid-template-columns:1fr}}

  .err{background:#fbecea; border:1px solid #f0c4bd; color:var(--red);
    padding:13px 16px; border-radius:10px; font-size:13px; margin-top:18px}
</style>
</head>
<body>
  <div class="card">
    <h1>Receive Payments</h1>
    <p class="sub">Upload the monthly Y&amp;S or TicketVault sales ledgers to generate output files ready for QBO upload.</p>

    <div id="drop" class="drop">
      <div class="ico">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 16V4m0 0L8 8m4-4l4 4"/>
          <path d="M4 14v4a2 2 0 002 2h12a2 2 0 002-2v-4"/>
        </svg>
      </div>
      <div class="big">Drag &amp; drop your <b>Excel or CSV</b> files here, or <span class="browse">browse</span></div>
      <div class="small">Accepts .xlsx, .xlsm, .csv &mdash; select multiple files to merge</div>
    </div>
    <input type="file" id="fileInput" multiple accept=".xlsx,.xlsm,.csv">
    <div id="filelist" class="filelist"></div>
    <div class="actions">
      <button id="go" class="go" disabled>Process ledger</button>
      <button id="clear" class="clear" type="button">Clear</button>
    </div>

    <div id="errBox"></div>

    <section id="panel" class="panel">
      <div id="status" class="status"><div class="spinner"></div><span>Processing&hellip;</span></div>
      <div id="results" style="display:none">
        <p class="daterange">Date range: <b id="daterange"></b></p>

        <a id="dlZip" class="dlcard" href="#">
          <span class="dlcard-ico">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 4v10m0 0l-3.5-3.5M12 14l3.5-3.5"/>
              <path d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2"/>
            </svg>
          </span>
          <span class="dlcard-txt">
            <b>Download All (.zip)</b>
            <span>Includes combined file + all company files</span>
          </span>
        </a>

        <div class="seclabel">Summary</div>
        <table class="summary">
          <thead><tr><th>Company</th><th class="num">Rows</th><th class="num">Amount Received</th></tr></thead>
          <tbody id="rows"></tbody>
        </table>

        <div class="seclabel">Individual company files</div>
        <div class="filegrid" id="filegrid"></div>
      </div>
    </section>
  </div>

<script>
const drop=document.getElementById('drop'),input=document.getElementById('fileInput'),
      filelist=document.getElementById('filelist'),go=document.getElementById('go'),
      panel=document.getElementById('panel'),statusEl=document.getElementById('status'),
      results=document.getElementById('results'),rowsEl=document.getElementById('rows'),
      errBox=document.getElementById('errBox');
let files=[];

const money=n=>'$'+Number(n||0).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
const FILEICO='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8z"/><path d="M14 3v5h5"/></svg>';

function render(){
  filelist.innerHTML=files.map(f=>`<div class="filerow"><span>${f.name}</span><span>${(f.size/1024).toFixed(0)} KB</span></div>`).join('');
  go.disabled=files.length===0;
}
drop.onclick=()=>input.click();
input.onchange=e=>{files=[...e.target.files];render()};
['dragover','dragenter'].forEach(ev=>drop.addEventListener(ev,e=>{e.preventDefault();drop.classList.add('over')}));
['dragleave','drop'].forEach(ev=>drop.addEventListener(ev,e=>{e.preventDefault();drop.classList.remove('over')}));
drop.addEventListener('drop',e=>{files=[...e.dataTransfer.files];render()});

document.getElementById('clear').onclick=()=>{
  files=[];
  input.value='';
  filelist.innerHTML='';
  errBox.innerHTML='';
  panel.classList.remove('show');
  results.style.display='none';
  rowsEl.innerHTML='';
  document.getElementById('filegrid').innerHTML='';
  go.disabled=true;
};

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
  errBox.innerHTML=`<div class="err">&#9888; ${msg}</div>`;
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
  document.getElementById('dlZip').href=`/download/${id}/all`;
  const withFiles=new Set(j.companies);
  const stats=j.stats||{};

  const comb=stats['Combined']||{rows:0,total:0};
  let rowsHtml=`<tr class="combined-row"><td>Combined</td><td class="num">${comb.rows}</td><td class="num">${money(comb.total)}</td></tr>`;
  j.all_companies.forEach(c=>{
    const s=stats[c]||{rows:0,total:0};
    rowsHtml+=`<tr class="${s.rows?'':'zero'}"><td>${c}</td><td class="num">${s.rows}</td><td class="num">${money(s.total)}</td></tr>`;
  });
  rowsEl.innerHTML=rowsHtml;

  let grid=`<a class="fcard has" href="/download/${id}/combined"><span class="fcard-ico">${FILEICO}</span><span class="fcard-name">Combined</span></a>`;
  j.all_companies.forEach(c=>{
    if(withFiles.has(c)){
      grid+=`<a class="fcard has" href="/download/${id}/company/${encodeURIComponent(c)}"><span class="fcard-ico">${FILEICO}</span><span class="fcard-name">${c}</span></a>`;
    }else{
      grid+=`<div class="fcard no"><span class="fcard-ico">${FILEICO}</span><span class="fcard-txt"><span class="fcard-name">${c}</span><span class="fcard-sub">No data</span></span></div>`;
    }
  });
  document.getElementById('filegrid').innerHTML=grid;
}
</script>
</body>
</html>
"""


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


@app.route("/favicon.ico")
def favicon():
    return ("", 204)


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
