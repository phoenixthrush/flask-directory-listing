import importlib.metadata
import mimetypes
import os
import tempfile
import zipfile
from datetime import datetime
from urllib.parse import quote, unquote

from flask import Flask, abort, jsonify, render_template, request, send_file

app = Flask(__name__)

SERVE_ROOT = os.path.join(os.path.dirname(__file__), "apache", "share")
ICON_PATH = "icons/"
# Apache-style sorting configuration (False = directories first, True = mixed like Apache)
APACHE_STYLE_SORTING = False
try:
    flask_version = importlib.metadata.version("flask")
    SERVER_NAME = f"Flask/{flask_version} Server"
except Exception:
    SERVER_NAME = "Flask Server"
SERVER_VERSION = ""

# File type to icon mapping
ICON_MAP = {
    # Directories
    "directory": "folder.gif",
    "parent": "back.gif",
    # Images
    "image/jpeg": "image2.gif",
    "image/jpg": "image2.gif",
    "image/png": "image2.gif",
    "image/gif": "image2.gif",
    "image/webp": "image2.gif",
    "image/svg+xml": "image2.gif",
    # Documents
    "application/pdf": "layout.gif",
    "text/plain": "text.gif",
    "text/html": "layout.gif",
    "application/msword": "layout.gif",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "layout.gif",
    # Archives
    "application/zip": "compressed.gif",
    "application/x-7z-compressed": "unknown.gif",
    "application/x-rar-compressed": "compressed.gif",
    "application/x-tar": "compressed.gif",
    "application/gzip": "compressed.gif",
    # Video
    "video/mp4": "movie.gif",
    "video/webm": "movie.gif",
    "video/quicktime": "movie.gif",
    "video/x-msvideo": "movie.gif",
    # Audio
    "audio/mpeg": "sound1.gif",
    "audio/wav": "sound1.gif",
    "audio/ogg": "sound1.gif",
    # Code files
    "text/x-python": "text.gif",
    "application/javascript": "text.gif",
    "text/css": "text.gif",
    "text/x-c": "c.gif",
    # Default
    "default": "unknown.gif",
}


def get_file_icon(file_path, is_directory=False):
    if is_directory:
        return ICON_MAP["directory"]

    mime_type, _ = mimetypes.guess_type(file_path)
    return ICON_MAP.get(mime_type, ICON_MAP["default"])


def get_file_type_label(file_path, is_directory=False):
    if is_directory:
        return "DIR"

    # Special case for 7z files - use exact filename check
    if file_path.lower().endswith(".7z"):
        return "   "

    mime_type, _ = mimetypes.guess_type(file_path)
    if mime_type:
        if mime_type.startswith("image/"):
            return "IMG"
        elif mime_type.startswith("video/"):
            return "VID"
        elif mime_type.startswith("audio/"):
            return "AUD"
        elif mime_type == "application/pdf":
            return "   "
        elif mime_type == "text/plain":
            return "TXT"
        elif "compressed" in mime_type or "zip" in mime_type:
            return "ARC"

    return "   "


def format_file_size(size_bytes):
    """Format file size in Apache-style format."""
    if size_bytes == 0:
        return "  0 "

    # Apache-style formatting with decimal places
    if size_bytes < 1024:
        return f"{size_bytes:3d} "
    elif size_bytes < 1024 * 1024:
        size_k = size_bytes / 1024.0
        if size_k < 10:
            return f"{size_k:.1f}K"
        else:
            return f"{size_k:3.0f}K"
    elif size_bytes < 1024 * 1024 * 1024:
        size_m = size_bytes / (1024.0 * 1024.0)
        if size_m < 10:
            return f"{size_m:.1f}M"
        else:
            return f"{size_m:3.0f}M"
    else:
        size_g = size_bytes / (1024.0 * 1024.0 * 1024.0)
        if size_g < 10:
            return f"{size_g:.1f}G"
        else:
            return f"{size_g:3.0f}G"


def get_directory_listing(
    directory_path, sort_by="name", sort_order="A", apache_style=None
):
    """Get a list of files and directories in the given path."""
    if apache_style is None:
        apache_style = APACHE_STYLE_SORTING

    files = []

    try:
        for item in os.listdir(directory_path):
            item_path = os.path.join(directory_path, item)

            # Skip hidden files (starting with .)
            if item.startswith("."):
                continue

            is_directory = os.path.isdir(item_path)
            stat = os.stat(item_path)

            file_info = {
                "name": item,
                "href": quote(item) + ("/" if is_directory else ""),
                "icon": get_file_icon(item, is_directory),
                "type": get_file_type_label(item, is_directory),
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime(
                    "%Y-%m-%d %H:%M"
                ),
                "modified_timestamp": stat.st_mtime,
                "size": format_file_size(stat.st_size) if not is_directory else "  - ",
                "size_formatted": format_file_size(stat.st_size)
                if not is_directory
                else "  - ",
                "size_bytes": stat.st_size if not is_directory else 0,
                "description": "",
                "is_directory": is_directory,
            }
            files.append(file_info)

    except (OSError, PermissionError):
        return []

    # Sort files based on style preference
    if apache_style:
        # Apache sorts all items together, not directories first
        # Apache uses case-sensitive lexicographic sorting (ASCII order)
        if sort_by == "name":
            # Use case-sensitive sort like Apache
            files.sort(key=lambda x: x["name"])
        elif sort_by == "modified":
            files.sort(key=lambda x: x["modified_timestamp"])
        elif sort_by == "size":
            files.sort(key=lambda x: x["size_bytes"])
        elif sort_by == "description":
            files.sort(key=lambda x: x["description"])
    else:
        # Intuitive sorting: directories first, then files
        if sort_by == "name":
            files.sort(key=lambda x: (not x["is_directory"], x["name"]))
        elif sort_by == "modified":
            files.sort(key=lambda x: (not x["is_directory"], x["modified_timestamp"]))
        elif sort_by == "size":
            files.sort(key=lambda x: (not x["is_directory"], x["size_bytes"]))
        elif sort_by == "description":
            files.sort(key=lambda x: (not x["is_directory"], x["description"]))

    if sort_order == "D":
        files.reverse()

    return files


def get_sort_url(request_path, column, current_column, current_order):
    """Generate sort URL with proper order toggle logic matching Apache."""
    # Use the global configuration for apache_style
    apache_style = APACHE_STYLE_SORTING

    if column == current_column:
        # If clicking on the same column, reverse the order
        new_order = "D" if current_order == "A" else "A"
    else:
        # Default sort orders for each column when first clicked
        if column == "N":  # Name - default ascending
            new_order = "D" if apache_style else "A"  # Apache shows descending first
        elif column == "M":  # Modified - default ascending
            new_order = "A"
        elif column == "S":  # Size - default ascending
            new_order = "A"
        elif column == "D":  # Description - default ascending
            new_order = "A"
        else:
            new_order = "A"

    # Use relative URL like Apache
    return f"?C={column};O={new_order}"


@app.route("/")
@app.route("/<path:subpath>")
def directory_listing(subpath=""):
    """Handle directory listing requests."""
    # Decode URL path
    subpath = unquote(subpath)

    # Construct full path
    full_path = os.path.join(SERVE_ROOT, subpath)
    full_path = os.path.normpath(full_path)

    # Security check - ensure we're still within SERVE_ROOT
    if not full_path.startswith(os.path.normpath(SERVE_ROOT)):
        abort(403)

    # Check if path exists
    if not os.path.exists(full_path):
        abort(404)

    # If it's a file, serve it
    if os.path.isfile(full_path):
        return send_file(full_path)

    # If it's a directory, check for download request first
    if os.path.isdir(full_path):
        # Check if this is a ZIP download request
        download_param = request.args.get("download")
        if download_param:
            return download_directory_as_zip(full_path, download_param, subpath)

        # Get sorting parameters - handle Apache's semicolon separator manually
        query_string = request.query_string.decode("utf-8")
        sort_column = "N"  # default
        sort_order = "A"  # default
        apache_style = APACHE_STYLE_SORTING  # default from config

        if query_string:
            # Parse Apache-style parameters with semicolon separator
            params = {}
            for param in query_string.replace(";", "&").split("&"):
                if "=" in param:
                    key, value = param.split("=", 1)
                    params[key] = value

            sort_column = params.get("C", "N")
            sort_order = params.get("O", "A")

            # Handle apache parameter
            apache_param = params.get("apache", "").lower()
            if apache_param in ["true", "1", "yes"]:
                apache_style = True
            elif apache_param in ["false", "0", "no"]:
                apache_style = False

        sort_map = {"N": "name", "M": "modified", "S": "size", "D": "description"}
        sort_by = sort_map.get(sort_column, "name")

        # Get file listing
        files = get_directory_listing(full_path, sort_by, sort_order, apache_style)

        # Determine parent directory
        parent_dir = None
        if subpath:  # Not at root
            parent_path = os.path.dirname(subpath.rstrip("/"))
            if parent_path:
                parent_dir = "/" + parent_path + "/"
            else:
                parent_dir = "/"

        # Current path for display
        display_path = "/" + subpath.rstrip("/") if subpath else "/"

        # Server info to match Apache format
        port = request.host.split(":")[1] if ":" in request.host else "5001"
        server_info = f"{SERVER_NAME} at {request.host.split(':')[0]} Port {port}"

        return render_template(
            "index.html",
            path=display_path,
            icon_path=ICON_PATH,
            parent_dir=parent_dir,
            sort_by=sort_by,
            sort_order=sort_order,
            sort_column=sort_column,
            server_info=server_info,
            files=files,
            get_sort_url=get_sort_url,
        )

    abort(404)


@app.route("/", methods=["POST"])
@app.route("/<path:subpath>", methods=["POST"])
def upload_file(subpath=""):
    """Handle file upload requests."""
    # Decode URL path
    subpath = unquote(subpath)

    # Construct full path
    full_path = os.path.join(SERVE_ROOT, subpath)
    full_path = os.path.normpath(full_path)

    # Security check - ensure we're still within SERVE_ROOT
    if not full_path.startswith(os.path.normpath(SERVE_ROOT)):
        return jsonify({"success": False, "error": "Access denied"}), 403

    # Check if directory exists
    if not os.path.exists(full_path) or not os.path.isdir(full_path):
        return jsonify({"success": False, "error": "Directory not found"}), 404

    # Check if this is an upload request
    if "upload" not in request.args:
        return jsonify({"success": False, "error": "Invalid request"}), 400

    # Check if file was uploaded
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file uploaded"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"success": False, "error": "No file selected"}), 400

    try:
        # Get the file and path from the form
        filename = file.filename
        relative_path = request.form.get(
            "path", filename
        )  # Use 'path' if provided, otherwise filename

        # Normalize the relative path (remove any leading slashes, handle backslashes)
        relative_path = relative_path.replace("\\", "/").lstrip("/")

        print(f"Uploading file: {filename} with path: {relative_path}")  # Debug logging

        # Create the full file path, preserving directory structure
        if "/" in relative_path:
            # This is a file within a directory structure
            dir_structure = os.path.dirname(relative_path)
            filename = os.path.basename(relative_path)

            # Create the directory structure if it doesn't exist
            target_dir = os.path.join(full_path, dir_structure)
            target_dir = os.path.normpath(target_dir)

            print(f"Creating directory structure: {target_dir}")  # Debug logging

            # Security check for the directory path
            if not target_dir.startswith(full_path):
                return jsonify(
                    {"success": False, "error": "Invalid directory path"}
                ), 400

            # Create all necessary parent directories
            try:
                os.makedirs(target_dir, exist_ok=True)
                print(f"Successfully created directory: {target_dir}")  # Debug logging
            except OSError as e:
                print(f"Error creating directory {target_dir}: {e}")  # Debug logging
                return jsonify(
                    {"success": False, "error": f"Failed to create directory: {str(e)}"}
                ), 500

            file_path = os.path.join(target_dir, filename)
        else:
            # Simple file upload to current directory
            file_path = os.path.join(full_path, filename)

        file_path = os.path.normpath(file_path)
        print(f"Final file path: {file_path}")  # Debug logging

        # Final security check
        if not file_path.startswith(full_path):
            return jsonify({"success": False, "error": "Invalid filename"}), 400

        file.save(file_path)
        print(f"Successfully saved file: {file_path}")  # Debug logging
        return jsonify(
            {"success": True, "message": f"File {relative_path} uploaded successfully"}
        )

    except Exception as e:
        print(f"Upload error: {str(e)}")  # Debug logging
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/icons/<path:filename>")
def serve_assets(filename):
    """Serve static assets (icons, CSS, JS, etc.)."""
    assets_dir = os.path.join(os.path.dirname(__file__), "assets", "icons")
    file_path = os.path.join(assets_dir, filename)
    file_path = os.path.normpath(file_path)

    # Security check - ensure we're still within assets directory
    if not file_path.startswith(os.path.normpath(assets_dir)):
        abort(403)

    # Check if file exists
    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        abort(404)

    return send_file(file_path)


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    port = request.host.split(":")[1] if ":" in request.host else "5001"
    host = request.host.split(":")[0]
    return (
        f"""<!DOCTYPE HTML PUBLIC "-//IETF//DTD HTML 2.0//EN">
<html><head>
<title>404 Not Found</title>
</head><body>
<h1>Not Found</h1>
<p>The requested URL was not found on this server.</p>
<hr>
<address>{SERVER_NAME} at {host} Port {port}</address>
</body></html>""",
        404,
    )


@app.errorhandler(403)
def forbidden(error):
    """Handle 403 errors."""
    port = request.host.split(":")[1] if ":" in request.host else "5001"
    host = request.host.split(":")[0]
    return (
        f"""<!DOCTYPE HTML PUBLIC "-//IETF//DTD HTML 2.0//EN">
<html><head>
<title>403 Forbidden</title>
</head><body>
<h1>Forbidden</h1>
<p>You don't have permission to access this resource.</p>
<hr>
<address>{SERVER_NAME} at {host} Port {port}</address>
</body></html>""",
        403,
    )


def download_directory_as_zip(full_path, download_param, subpath):
    """Create and send a ZIP file of the requested directory."""
    try:
        # Validate the directory name matches what was requested
        target_dir = os.path.join(full_path, download_param)
        target_dir = os.path.normpath(target_dir)

        # Security check - ensure we're still within SERVE_ROOT
        if not target_dir.startswith(os.path.normpath(SERVE_ROOT)):
            abort(403)

        # Check if the target directory exists
        if not os.path.exists(target_dir) or not os.path.isdir(target_dir):
            abort(404)

        # Create a temporary ZIP file
        temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
        temp_zip.close()

        with zipfile.ZipFile(temp_zip.name, "w", zipfile.ZIP_DEFLATED) as zipf:
            # Walk through the directory and add all files
            for root, dirs, files in os.walk(target_dir):
                for file in files:
                    # Skip hidden files
                    if file.startswith("."):
                        continue

                    file_path = os.path.join(root, file)
                    # Calculate the relative path within the ZIP
                    arc_name = os.path.relpath(file_path, target_dir)
                    zipf.write(file_path, arc_name)

        # Clean up function to delete temp file after sending
        def remove_file(response):
            try:
                os.unlink(temp_zip.name)
            except Exception:
                pass
            return response

        # Send the ZIP file
        zip_filename = f"{download_param}.zip"
        response = send_file(
            temp_zip.name,
            as_attachment=True,
            download_name=zip_filename,
            mimetype="application/zip",
        )

        # Register cleanup function
        response.call_on_close(lambda: os.unlink(temp_zip.name))

        return response

    except Exception as e:
        print(f"ZIP download error: {str(e)}")
        abort(500)


if __name__ == "__main__":
    # Ensure the serve directory exists
    if not os.path.exists(SERVE_ROOT):
        print(f"Warning: Serve directory '{SERVE_ROOT}' does not exist!")
        print(f"Creating directory: {SERVE_ROOT}")
        os.makedirs(SERVE_ROOT, exist_ok=True)

    print("Starting Flask Directory Server...")
    print(f"Serving directory: {SERVE_ROOT}")
    print("Server will be available at: http://localhost:5001")

    app.run(debug=True, host="0.0.0.0", port=5001)
