import os
import mimetypes
from datetime import datetime
from urllib.parse import quote, unquote
import importlib.metadata

from flask import Flask, render_template, request, send_file, abort

app = Flask(__name__)

SERVE_ROOT = os.path.join(os.path.dirname(__file__), 'apache', 'share')
ICON_PATH = 'icons/'
try:
    flask_version = importlib.metadata.version("flask")
    SERVER_NAME = f'Flask/{flask_version} Server'
except Exception:
    SERVER_NAME = 'Flask Server'
SERVER_VERSION = ''

# File type to icon mapping
ICON_MAP = {
    # Directories
    'directory': 'folder.gif',
    'parent': 'back.gif',

    # Images
    'image/jpeg': 'image2.gif',
    'image/jpg': 'image2.gif',
    'image/png': 'image2.gif',
    'image/gif': 'image2.gif',
    'image/webp': 'image2.gif',
    'image/svg+xml': 'image2.gif',

    # Documents
    'application/pdf': 'layout.gif',
    'text/plain': 'text.gif',
    'text/html': 'layout.gif',
    'application/msword': 'layout.gif',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'layout.gif',

    # Archives
    'application/zip': 'compressed.gif',
    'application/x-7z-compressed': 'unknown.gif',
    'application/x-rar-compressed': 'compressed.gif',
    'application/x-tar': 'compressed.gif',
    'application/gzip': 'compressed.gif',

    # Video
    'video/mp4': 'movie.gif',
    'video/webm': 'movie.gif',
    'video/quicktime': 'movie.gif',
    'video/x-msvideo': 'movie.gif',

    # Audio
    'audio/mpeg': 'sound1.gif',
    'audio/wav': 'sound1.gif',
    'audio/ogg': 'sound1.gif',

    # Code files
    'text/x-python': 'text.gif',
    'application/javascript': 'text.gif',
    'text/css': 'text.gif',
    'text/x-c': 'c.gif',

    # Default
    'default': 'unknown.gif'
}


def get_file_icon(file_path, is_directory=False):
    if is_directory:
        return ICON_MAP['directory']

    mime_type, _ = mimetypes.guess_type(file_path)
    return ICON_MAP.get(mime_type, ICON_MAP['default'])


def get_file_type_label(file_path, is_directory=False):
    if is_directory:
        return 'DIR'

    # Special case for 7z files - use exact filename check
    if file_path.lower().endswith('.7z'):
        return '   '

    mime_type, _ = mimetypes.guess_type(file_path)
    if mime_type:
        if mime_type.startswith('image/'):
            return 'IMG'
        elif mime_type.startswith('video/'):
            return 'VID'
        elif mime_type.startswith('audio/'):
            return 'AUD'
        elif mime_type == 'application/pdf':
            return '   '
        elif mime_type == 'text/plain':
            return 'TXT'
        elif 'compressed' in mime_type or 'zip' in mime_type:
            return 'ARC'

    return '   '


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


def get_directory_listing(directory_path, sort_by='name', sort_order='A'):
    """Get a list of files and directories in the given path."""
    files = []

    try:
        for item in os.listdir(directory_path):
            item_path = os.path.join(directory_path, item)

            # Skip hidden files (starting with .)
            if item.startswith('.'):
                continue

            is_directory = os.path.isdir(item_path)
            stat = os.stat(item_path)

            file_info = {
                'name': item,
                'href': quote(item) + ('/' if is_directory else ''),
                'icon': get_file_icon(item, is_directory),
                'type': get_file_type_label(item, is_directory),
                'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M'),
                'modified_timestamp': stat.st_mtime,
                'size': format_file_size(stat.st_size) if not is_directory else '  - ',
                'size_formatted': format_file_size(stat.st_size) if not is_directory else '  - ',
                'size_bytes': stat.st_size if not is_directory else 0,
                'description': '',
                'is_directory': is_directory
            }
            files.append(file_info)

    except (OSError, PermissionError):
        return []

    # Sort files - Apache sorts all items together, not directories first
    # Apache uses case-sensitive lexicographic sorting (ASCII order)
    if sort_by == 'name':
        # Use case-sensitive sort like Apache
        files.sort(key=lambda x: x['name'])
    elif sort_by == 'modified':
        files.sort(key=lambda x: x['modified_timestamp'])
    elif sort_by == 'size':
        files.sort(key=lambda x: x['size_bytes'])
    elif sort_by == 'description':
        files.sort(key=lambda x: x['description'])

    if sort_order == 'D':
        files.reverse()

    return files


def get_sort_url(request_path, column, current_column, current_order):
    """Generate sort URL with proper order toggle logic matching Apache."""
    if column == current_column:
        # If clicking on the same column, reverse the order
        new_order = 'D' if current_order == 'A' else 'A'
    else:
        # Default sort orders for each column when first clicked
        if column == 'N':  # Name - default ascending
            new_order = 'D'  # But Apache shows descending first
        elif column == 'M':  # Modified - default ascending
            new_order = 'A'
        elif column == 'S':  # Size - default ascending
            new_order = 'A'
        elif column == 'D':  # Description - default ascending
            new_order = 'A'
        else:
            new_order = 'A'

    # Use relative URL like Apache
    return f"?C={column};O={new_order}"


@app.route('/')
@app.route('/<path:subpath>')
def directory_listing(subpath=''):
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

    # If it's a directory, show listing
    if os.path.isdir(full_path):
        # Get sorting parameters - handle Apache's semicolon separator manually
        query_string = request.query_string.decode('utf-8')
        sort_column = 'N'  # default
        sort_order = 'A'   # default

        if query_string:
            # Parse Apache-style parameters with semicolon separator
            params = {}
            for param in query_string.replace(';', '&').split('&'):
                if '=' in param:
                    key, value = param.split('=', 1)
                    params[key] = value

            sort_column = params.get('C', 'N')
            sort_order = params.get('O', 'A')

        sort_map = {
            'N': 'name',
            'M': 'modified',
            'S': 'size',
            'D': 'description'
        }
        sort_by = sort_map.get(sort_column, 'name')

        # Get file listing
        files = get_directory_listing(full_path, sort_by, sort_order)

        # Determine parent directory
        parent_dir = None
        if subpath:  # Not at root
            parent_path = os.path.dirname(subpath.rstrip('/'))
            if parent_path:
                parent_dir = '/' + parent_path + '/'
            else:
                parent_dir = '/'

        # Current path for display
        display_path = '/' + subpath.rstrip('/') if subpath else '/'

        # Server info to match Apache format
        port = request.host.split(':')[1] if ':' in request.host else '5001'
        server_info = f"Apache/2.4.62 (Ubuntu) Server at {request.host.split(':')[0]} Port {port}"

        return render_template('index.html',
                               path=display_path,
                               icon_path=ICON_PATH,
                               parent_dir=parent_dir,
                               sort_by=sort_by,
                               sort_order=sort_order,
                               sort_column=sort_column,
                               server_info=server_info,
                               files=files,
                               get_sort_url=get_sort_url)

    abort(404)


@app.route('/icons/<path:filename>')
def serve_assets(filename):
    """Serve static assets (icons, CSS, JS, etc.)."""
    assets_dir = os.path.join(os.path.dirname(__file__), 'assets', 'icons')
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
    return f"<h1>404 Not Found</h1><p>The requested URL was not found on this server.</p>", 404


@app.errorhandler(403)
def forbidden(error):
    """Handle 403 errors."""
    return f"<h1>403 Forbidden</h1><p>You don't have permission to access this resource.</p>", 403


if __name__ == '__main__':
    # Ensure the serve directory exists
    if not os.path.exists(SERVE_ROOT):
        print(f"Warning: Serve directory '{SERVE_ROOT}' does not exist!")
        print(f"Creating directory: {SERVE_ROOT}")
        os.makedirs(SERVE_ROOT, exist_ok=True)

    print(f"Starting Flask Directory Server...")
    print(f"Serving directory: {SERVE_ROOT}")
    print(f"Server will be available at: http://localhost:5001")

    app.run(debug=True, host='0.0.0.0', port=5001)
