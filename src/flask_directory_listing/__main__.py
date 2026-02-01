import argparse
import importlib.metadata
import mimetypes
import os
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote

from flask import Flask, abort, jsonify, render_template, request, send_file

app = Flask(__name__)


DEFAULT_ROOT = (Path.cwd() / "share").resolve()
ICON_PATH = "icons/"

ICON_MAP = {
    "directory": "folder.gif",
    "parent": "back.gif",
    "image/jpeg": "image2.gif",
    "image/jpg": "image2.gif",
    "image/png": "image2.gif",
    "image/gif": "image2.gif",
    "image/webp": "image2.gif",
    "image/svg+xml": "image2.gif",
    "application/pdf": "layout.gif",
    "text/plain": "text.gif",
    "text/html": "layout.gif",
    "application/msword": "layout.gif",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "layout.gif",
    "application/zip": "compressed.gif",
    "application/x-7z-compressed": "unknown.gif",
    "application/x-rar-compressed": "compressed.gif",
    "application/x-tar": "compressed.gif",
    "application/gzip": "compressed.gif",
    "video/mp4": "movie.gif",
    "video/webm": "movie.gif",
    "video/quicktime": "movie.gif",
    "video/x-msvideo": "movie.gif",
    "audio/mpeg": "sound1.gif",
    "audio/wav": "sound1.gif",
    "audio/ogg": "sound1.gif",
    "text/x-python": "text.gif",
    "application/javascript": "text.gif",
    "text/css": "text.gif",
    "text/x-c": "c.gif",
    "default": "unknown.gif",
}


def config():
    return app.config


def server_name():
    try:
        flask_version = importlib.metadata.version("flask")
        return f"Flask/{flask_version} Server"
    except Exception:
        return "Flask Server"


def inside_root(candidate: Path) -> bool:
    root = config()["SERVE_ROOT"]
    try:
        return candidate.resolve().is_relative_to(root)
    except AttributeError:
        return os.path.commonpath(
            [str(candidate.resolve()), str(root.resolve())]
        ) == str(root.resolve())


def format_size(size: int) -> str:
    if size == 0:
        return "  0 "
    step = 1024.0
    if size < step:
        return f"{size:3d} "
    size_k = size / step
    if size_k < step:
        return f"{size_k:.1f}K" if size_k < 10 else f"{size_k:3.0f}K"
    size_m = size_k / step
    if size_m < step:
        return f"{size_m:.1f}M" if size_m < 10 else f"{size_m:3.0f}M"
    size_g = size_m / step
    return f"{size_g:.1f}G" if size_g < 10 else f"{size_g:3.0f}G"


def file_icon(path: Path, is_dir: bool) -> str:
    if is_dir:
        return ICON_MAP["directory"]
    mime, _ = mimetypes.guess_type(path.name)
    return ICON_MAP.get(mime or "default", ICON_MAP["default"])


def file_label(path: Path, is_dir: bool) -> str:
    if is_dir:
        return "DIR"
    if path.suffix.lower() == ".7z":
        return "   "
    mime, _ = mimetypes.guess_type(path.name)
    if mime:
        if mime.startswith("image/"):
            return "IMG"
        if mime.startswith("video/"):
            return "VID"
        if mime.startswith("audio/"):
            return "AUD"
        if mime == "application/pdf":
            return "   "
        if mime == "text/plain":
            return "TXT"
        if "compressed" in mime or "zip" in mime:
            return "ARC"
    return "   "


def directory_listing_data(
    directory: Path, sort_by: str, sort_order: str, apache_style: bool
):
    entries = []
    try:
        for item in directory.iterdir():
            if item.name.startswith("."):
                continue
            is_dir = item.is_dir()
            stat = item.stat()
            entries.append(
                {
                    "name": item.name,
                    "href": quote(item.name) + ("/" if is_dir else ""),
                    "icon": file_icon(item, is_dir),
                    "type": file_label(item, is_dir),
                    "modified": datetime.fromtimestamp(stat.st_mtime).strftime(
                        "%Y-%m-%d %H:%M"
                    ),
                    "modified_timestamp": stat.st_mtime,
                    "size_formatted": format_size(stat.st_size)
                    if not is_dir
                    else "  - ",
                    "size_bytes": stat.st_size if not is_dir else 0,
                    "description": "",
                    "is_directory": is_dir,
                }
            )
    except (OSError, PermissionError):
        return []

    def sort_key(entry):
        value = {
            "name": entry["name"],
            "modified": entry["modified_timestamp"],
            "size": entry["size_bytes"],
            "description": entry["description"],
        }[sort_by]
        return value if apache_style else (not entry["is_directory"], value)

    entries.sort(key=sort_key)
    if sort_order == "D":
        entries.reverse()
    return entries


def sort_url(column, current_column, current_order):
    apache_style = config()["APACHE_STYLE_SORTING"]
    if column == current_column:
        new_order = "D" if current_order == "A" else "A"
    else:
        new_order = "D" if column == "N" and apache_style else "A"
    return f"?C={column};O={new_order}"


@app.route("/")
@app.route("/<path:subpath>")
def list_endpoint(subpath=""):
    subpath = unquote(subpath)
    root = config()["SERVE_ROOT"]
    target = (root / subpath).resolve()
    if not inside_root(target):
        abort(403)
    if not target.exists():
        abort(404)
    if target.is_file():
        return send_file(target)

    download_name = request.args.get("download")
    if download_name:
        return download_directory_as_zip(target, download_name)

    raw_query = request.query_string.decode("utf-8").replace(";", "&")
    params = {k: v[0] for k, v in parse_qs(raw_query).items() if v}
    sort_column = params.get("C", "N")
    sort_order = params.get("O", "A")
    apache_style = config()["APACHE_STYLE_SORTING"]
    apache_flag = params.get("apache", "").lower()
    if apache_flag in ("true", "1", "yes"):
        apache_style = True
    elif apache_flag in ("false", "0", "no"):
        apache_style = False

    sort_map = {"N": "name", "M": "modified", "S": "size", "D": "description"}
    sort_by = sort_map.get(sort_column, "name")

    files = directory_listing_data(target, sort_by, sort_order, apache_style)
    parent_dir = None
    if subpath:
        parent = "/" + subpath.rstrip("/")
        parent_dir = os.path.dirname(parent) + "/"
        if parent_dir == "//":
            parent_dir = "/"

    port = request.host.split(":")[1] if ":" in request.host else str(config()["PORT"])
    info = f"{config()['SERVER_BANNER']} at {request.host.split(':')[0]} Port {port}"

    return render_template(
        "index.html",
        path="/" + subpath.rstrip("/") if subpath else "/",
        icon_path=ICON_PATH,
        parent_dir=parent_dir,
        sort_by=sort_by,
        sort_order=sort_order,
        sort_column=sort_column,
        server_info=info,
        files=files,
        get_sort_url=lambda path, col, cur, order: sort_url(col, cur, order),
    )


@app.route("/", methods=["POST"])
@app.route("/<path:subpath>", methods=["POST"])
def upload_endpoint(subpath=""):
    subpath = unquote(subpath)
    root = config()["SERVE_ROOT"]
    target_dir = (root / subpath).resolve()
    if not inside_root(target_dir):
        return jsonify({"success": False, "error": "Access denied"}), 403
    if not target_dir.exists() or not target_dir.is_dir():
        return jsonify({"success": False, "error": "Directory not found"}), 404
    if "upload" not in request.args:
        return jsonify({"success": False, "error": "Invalid request"}), 400
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file uploaded"}), 400

    upload = request.files["file"]
    if not upload.filename:
        return jsonify({"success": False, "error": "No file selected"}), 400

    relative_path = (
        request.form.get("path", upload.filename).replace("\\", "/").lstrip("/")
    )
    destination = (target_dir / relative_path).resolve()
    if not inside_root(destination):
        return jsonify({"success": False, "error": "Invalid path"}), 400
    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        upload.save(destination)
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500

    return jsonify(
        {"success": True, "message": f"File {relative_path} uploaded successfully"}
    )


@app.route("/icons/<path:filename>")
def serve_assets(filename):
    assets_dir = Path(__file__).resolve().parents[2] / "assets" / "icons"
    file_path = (assets_dir / filename).resolve()
    if not str(file_path).startswith(str(assets_dir)):
        abort(403)
    if not file_path.exists() or not file_path.is_file():
        abort(404)
    return send_file(file_path)


@app.errorhandler(404)
def not_found(_):
    port = request.host.split(":")[1] if ":" in request.host else str(config()["PORT"])
    host = request.host.split(":")[0]
    return (
        f"""<!DOCTYPE HTML PUBLIC "-//IETF//DTD HTML 2.0//EN">
<html><head><title>404 Not Found</title></head><body>
<h1>Not Found</h1>
<p>The requested URL was not found on this server.</p>
<hr><address>{config()["SERVER_BANNER"]} at {host} Port {port}</address>
</body></html>""",
        404,
    )


@app.errorhandler(403)
def forbidden(_):
    port = request.host.split(":")[1] if ":" in request.host else str(config()["PORT"])
    host = request.host.split(":")[0]
    return (
        f"""<!DOCTYPE HTML PUBLIC "-//IETF//DTD HTML 2.0//EN">
<html><head><title>403 Forbidden</title></head><body>
<h1>Forbidden</h1>
<p>You don't have permission to access this resource.</p>
<hr><address>{config()["SERVER_BANNER"]} at {host} Port {port}</address>
</body></html>""",
        403,
    )


def download_directory_as_zip(directory: Path, child: str):
    target = (directory / child).resolve()
    if not inside_root(target) or not target.is_dir():
        abort(403 if target.exists() else 404)

    temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    temp_zip.close()
    try:
        with zipfile.ZipFile(temp_zip.name, "w", zipfile.ZIP_DEFLATED) as zipf:
            for root_dir, _, files in os.walk(target):
                for name in files:
                    if name.startswith("."):
                        continue
                    file_path = Path(root_dir) / name
                    arc = file_path.relative_to(target)
                    zipf.write(file_path, arc)
        response = send_file(
            temp_zip.name,
            as_attachment=True,
            download_name=f"{child}.zip",
            mimetype="application/zip",
        )
        response.call_on_close(lambda: os.unlink(temp_zip.name))
        return response
    except Exception:
        os.unlink(temp_zip.name)
        abort(500)


def parse_args():
    parser = argparse.ArgumentParser(description="Simple Apache-style directory lister")
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="Directory to serve")
    parser.add_argument("--host", default="0.0.0.0", help="Listen address")
    parser.add_argument("--port", type=int, default=8080, help="Listen port")
    parser.add_argument("--debug", action="store_true", help="Enable Flask debug")
    parser.add_argument(
        "--apache-style",
        action="store_true",
        help="Use Apache-style mixed sorting (directories not forced first)",
    )
    return parser.parse_args()


def configure_from_args(options):
    root = Path(options.root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    app.config.update(
        SERVE_ROOT=root,
        APACHE_STYLE_SORTING=options.apache_style,
        SERVER_BANNER=server_name(),
        PORT=options.port,
    )
    return options


def main():
    args = configure_from_args(parse_args())
    print(
        f"Serving {config()['SERVE_ROOT']} on {args.host}:{args.port} (apache-style={config()['APACHE_STYLE_SORTING']})"
    )
    app.run(debug=args.debug, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
