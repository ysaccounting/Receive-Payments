import io
import os
import json
import zipfile
import threading
import uuid
import tempfile
from flask import Flask, request, jsonify, send_file, render_template
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
    return render_template("index.html")


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
